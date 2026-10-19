"""Create and verify encrypted, transaction-consistent SQLite backups.

The key must be stored separately from the encrypted archives.  Restores never
overwrite an existing database; stop the application and move the verified file
into place explicitly after reviewing it.
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


MAGIC = b"RTBK1"
NONCE_SIZE = 12
TAG_SIZE = 16
CHUNK_SIZE = 1024 * 1024


def _key(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("backup key must not be a symbolic link")
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError("backup key must be exactly 32 bytes")
    return key


def init_key(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("backup key must not be a symbolic link")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(secrets.token_bytes(32))
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _integrity_check(path: Path) -> None:
    # An immutable read avoids WAL sidecar files next to a restored archive.
    # The snapshot is already closed and cannot be changing during validation.
    connection = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise ValueError(f"SQLite integrity check failed: {result!r}")
        required = {"accounts", "manuscripts", "rewrite_jobs", "orders", "ledger_entries"}
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not required <= tables:
            raise ValueError(f"backup is missing required tables: {sorted(required - tables)}")
    finally:
        connection.close()


def _encrypt(source: Path, destination: Path, key: bytes) -> None:
    nonce = secrets.token_bytes(NONCE_SIZE)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    with source.open("rb") as plain, destination.open("xb") as sealed:
        os.chmod(destination, 0o600)
        sealed.write(MAGIC + nonce)
        while chunk := plain.read(CHUNK_SIZE):
            sealed.write(encryptor.update(chunk))
        sealed.write(encryptor.finalize())
        sealed.write(encryptor.tag)
        sealed.flush()
        os.fsync(sealed.fileno())


def _decrypt(archive: Path, destination: Path, key: bytes) -> None:
    size = archive.stat().st_size
    if size < len(MAGIC) + NONCE_SIZE + TAG_SIZE + 1:
        raise ValueError("backup archive is incomplete")
    with archive.open("rb") as sealed:
        header = sealed.read(len(MAGIC) + NONCE_SIZE)
        if not header.startswith(MAGIC):
            raise ValueError("not a RightThesis backup archive")
        nonce = header[len(MAGIC):]
        sealed.seek(-TAG_SIZE, os.SEEK_END)
        tag = sealed.read(TAG_SIZE)
        sealed.seek(len(header))
        remaining = size - len(header) - TAG_SIZE
        decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        with destination.open("xb") as plain:
            os.chmod(destination, 0o600)
            while remaining:
                chunk = sealed.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise ValueError("backup archive ended early")
                remaining -= len(chunk)
                plain.write(decryptor.update(chunk))
            plain.write(decryptor.finalize())
            plain.flush()
            os.fsync(plain.fileno())


def verify(archive: Path, key_path: Path) -> None:
    key = _key(key_path)
    with tempfile.TemporaryDirectory(prefix="rt-verify-", dir=archive.parent) as folder:
        plain = Path(folder) / "verified.sqlite3"
        _decrypt(archive, plain, key)
        _integrity_check(plain)


def backup(database: Path, output_dir: Path, key_path: Path) -> Path:
    if not database.is_file() or database.is_symlink():
        raise ValueError("source database must be a regular file")
    key = _key(key_path)
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValueError("backup directory must not be a symbolic link")
    usage = shutil.disk_usage(output_dir)
    if usage.free < max(database.stat().st_size * 3, 64 * 1024 * 1024):
        raise ValueError("not enough free space for a consistent database backup")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = output_dir / f"rightthesis-{stamp}-{secrets.token_hex(4)}.rtbk"
    with tempfile.TemporaryDirectory(prefix="rt-backup-", dir=output_dir) as folder:
        plain = Path(folder) / "snapshot.sqlite3"
        source = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=30)
        try:
            target = sqlite3.connect(plain)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        os.chmod(plain, 0o600)
        _integrity_check(plain)
        partial = Path(folder) / "archive.part"
        _encrypt(plain, partial, key)
        verify(partial, key_path)
        os.replace(partial, archive)
    return archive


def restore(archive: Path, destination: Path, key_path: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("restore destination already exists; refusing to overwrite it")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("restore temporary file already exists")
    try:
        _decrypt(archive, temporary, _key(key_path))
        _integrity_check(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("init-key", "backup", "verify", "restore"):
        command = commands.add_parser(action)
        command.add_argument("--key-file", type=Path, required=True)
        if action == "backup":
            command.add_argument("--database", type=Path, required=True)
            command.add_argument("--output-dir", type=Path, required=True)
        elif action in {"verify", "restore"}:
            command.add_argument("--archive", type=Path, required=True)
            if action == "restore":
                command.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "init-key":
        init_key(args.key_file)
        print("backup key created; store a copy outside this server")
    elif args.action == "backup":
        archive = backup(args.database, args.output_dir, args.key_file)
        print(f"verified encrypted backup: {archive}")
    elif args.action == "verify":
        verify(args.archive, args.key_file)
        print("backup integrity verified")
    else:
        restore(args.archive, args.destination, args.key_file)
        print(f"restored and verified: {args.destination}")


if __name__ == "__main__":
    main()

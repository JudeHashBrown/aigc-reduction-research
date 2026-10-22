"""Fail closed if the latest encrypted backup lacks a recent OSS success receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from backup_database import restore
from upload_oss_backup import newest_archive


def check(directory: Path, max_age_hours: float = 4,
          key_file: Path | None = None) -> dict:
    archive = newest_archive(directory, max_age_hours)
    receipt_path = directory / "oss-upload-receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("OSS upload receipt is missing")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("archive") != archive.name:
        raise ValueError("latest backup was not uploaded to OSS")
    if receipt.get("object") != "rightthesis-backups/" + archive.name:
        raise ValueError("OSS receipt object does not match archive")
    age = time.time() - float(receipt.get("uploaded_at", 0))
    if age < -300 or age > max_age_hours * 3600:
        raise ValueError("OSS receipt is stale")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != receipt.get("sha256"):
        raise ValueError("backup differs from the acknowledged OSS upload")
    if key_file is not None:
        # Exercise the same restore path operators use, without ever touching
        # the live database.  The upload credential is write-only, so this is
        # a local archive drill, not proof that OSS downloads work.
        with tempfile.TemporaryDirectory(prefix="rt-restore-drill-") as folder:
            restored = Path(folder) / "restored.sqlite3"
            restore(archive, restored, key_file)
            if not restored.is_file() or restored.stat().st_size == 0:
                raise ValueError("restored database is empty")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--max-age-hours", type=float, default=4)
    parser.add_argument("--key-file", type=Path,
                        help="run a restore drill into a temporary directory")
    args = parser.parse_args()
    if args.max_age_hours <= 0:
        parser.error("--max-age-hours must be positive")
    receipt = check(args.backup_dir, args.max_age_hours, args.key_file)
    label = "backup, OSS receipt and local restore" if args.key_file else "backup and OSS receipt"
    print(f"{label} healthy: {receipt['archive']}")


if __name__ == "__main__":
    main()

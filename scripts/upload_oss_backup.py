"""Verify and upload the newest encrypted SQLite backup to private Alibaba OSS.

The server credential only needs oss:PutObject on the configured object prefix.
Never upload the AES key or an unencrypted database to this bucket.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from backup_database import verify


MAX_SINGLE_PUT_BYTES = 5 * 1024**3
OBJECT_PREFIX = "rightthesis-backups/"


def newest_archive(directory: Path, max_age_hours: float = 6) -> Path:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("backup directory must be a real directory")
    archives = [path for path in directory.glob("rightthesis-*.rtbk")
                if not path.is_symlink() and path.is_file()]
    if not archives:
        raise ValueError("no encrypted backup archive is available")
    archive = max(archives, key=lambda path: path.stat().st_mtime)
    age_seconds = time.time() - archive.stat().st_mtime
    if age_seconds < -300 or age_seconds > max_age_hours * 3600:
        raise ValueError("newest backup is not recent; refusing to upload a stale archive")
    return archive


def upload(archive: Path, key_file: Path, bucket_name: str, region: str) -> str:
    if archive.is_symlink() or not archive.is_file() or archive.suffix != ".rtbk":
        raise ValueError("archive must be a regular encrypted .rtbk file")
    if archive.stat().st_size > MAX_SINGLE_PUT_BYTES:
        raise ValueError("archive exceeds the OSS single-upload limit")
    if not os.environ.get("OSS_ACCESS_KEY_ID") or not os.environ.get("OSS_ACCESS_KEY_SECRET"):
        raise ValueError("OSS upload credentials are not configured")
    if region != "cn-hongkong":
        raise ValueError("this deployment only permits the Hong Kong OSS region")
    if bucket_name != "rightthesis-backup-jude-2026":
        raise ValueError("unexpected OSS backup bucket")
    verify(archive, key_file)

    import oss2  # Installed only on the production server; tests inject a fake SDK.
    from oss2.credentials import EnvironmentVariableCredentialsProvider

    auth = oss2.ProviderAuthV4(EnvironmentVariableCredentialsProvider())
    client = oss2.Bucket(
        auth,
        "https://oss-cn-hongkong.aliyuncs.com",
        bucket_name,
        region=region,
    )
    object_name = OBJECT_PREFIX + archive.name
    result = client.put_object_from_file(object_name, str(archive))
    if result.status != 200:
        raise RuntimeError(f"OSS upload failed with HTTP {result.status}")
    return object_name


def record_success(directory: Path, archive: Path, object_name: str) -> Path:
    """Leave a local receipt only after OSS acknowledges the encrypted object."""
    if directory.is_symlink() or archive.parent.resolve() != directory.resolve():
        raise ValueError("archive and receipt must be in the backup directory")
    payload = {"archive": archive.name, "object": object_name,
               "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "uploaded_at": time.time()}
    receipt = directory / "oss-upload-receipt.json"
    temporary = directory / "oss-upload-receipt.json.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, receipt)
    finally:
        temporary.unlink(missing_ok=True)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--bucket", default="rightthesis-backup-jude-2026")
    parser.add_argument("--region", default="cn-hongkong")
    parser.add_argument("--max-age-hours", type=float, default=6)
    args = parser.parse_args()
    if args.max_age_hours <= 0:
        parser.error("--max-age-hours must be positive")
    archive = newest_archive(args.backup_dir, args.max_age_hours)
    name = upload(archive, args.key_file, args.bucket, args.region)
    record_success(args.backup_dir, archive, name)
    print(f"verified encrypted OSS backup uploaded: {args.bucket}/{name}")


if __name__ == "__main__":
    main()

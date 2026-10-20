"""Fail closed if the latest encrypted backup lacks a recent OSS success receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from upload_oss_backup import newest_archive


def check(directory: Path, max_age_hours: float = 4) -> dict:
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
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--max-age-hours", type=float, default=4)
    args = parser.parse_args()
    if args.max_age_hours <= 0:
        parser.error("--max-age-hours must be positive")
    receipt = check(args.backup_dir, args.max_age_hours)
    print(f"backup and OSS receipt healthy: {receipt['archive']}")


if __name__ == "__main__":
    main()

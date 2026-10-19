"""Offline checks for the least-privilege encrypted OSS upload path."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backup_database import backup, init_key  # noqa: E402
from upload_oss_backup import newest_archive, upload  # noqa: E402


def assert_rejected(action, expected: str) -> None:
    try:
        action()
    except ValueError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError(f"expected rejection: {expected}")


def test_upload_only_verified_encrypted_archive() -> None:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        database = root / "live.sqlite3"
        with sqlite3.connect(database) as connection:
            for table in ("accounts", "manuscripts", "rewrite_jobs", "orders", "ledger_entries"):
                connection.execute(f"CREATE TABLE {table} (value TEXT)")
        key = root / "backup.key"
        init_key(key)
        archive_dir = root / "archives"
        archive = backup(database, archive_dir, key)
        assert newest_archive(archive_dir) == archive

        old = archive_dir / "rightthesis-old.rtbk"
        old.write_bytes(archive.read_bytes())
        os.utime(old, (time.time() - 24 * 3600, time.time() - 24 * 3600))
        assert newest_archive(archive_dir) == archive
        assert_rejected(lambda: newest_archive(archive_dir, 0.0000001), "not recent")
        assert_rejected(lambda: newest_archive(root / "missing"), "real directory")
        link = archive_dir / "rightthesis-link.rtbk"
        link.symlink_to(archive)
        assert newest_archive(archive_dir) == archive

        assert_rejected(
            lambda: upload(archive, key, "rightthesis-backup-jude-2026", "cn-hongkong"),
            "credentials",
        )
        calls: list[tuple[str, str]] = []
        fake_oss2 = types.ModuleType("oss2")
        fake_credentials = types.ModuleType("oss2.credentials")
        fake_credentials.EnvironmentVariableCredentialsProvider = lambda: object()
        fake_oss2.ProviderAuthV4 = lambda provider: provider

        def fake_bucket(auth, endpoint, bucket_name, *, region):
            assert endpoint == "https://oss-cn-hongkong.aliyuncs.com"
            assert bucket_name == "rightthesis-backup-jude-2026"
            assert region == "cn-hongkong"

            class Bucket:
                @staticmethod
                def put_object_from_file(object_name, source):
                    calls.append((object_name, source))
                    return types.SimpleNamespace(status=200)

            return Bucket()

        fake_oss2.Bucket = fake_bucket
        with patch.dict(os.environ, {"OSS_ACCESS_KEY_ID": "test-id", "OSS_ACCESS_KEY_SECRET": "test-secret"}), \
             patch.dict(sys.modules, {"oss2": fake_oss2, "oss2.credentials": fake_credentials}):
            assert_rejected(lambda: upload(archive, key, "wrong", "cn-hongkong"), "bucket")
            assert_rejected(lambda: upload(archive, key, "rightthesis-backup-jude-2026", "us-east-1"), "region")
            assert_rejected(lambda: upload(link, key, "rightthesis-backup-jude-2026", "cn-hongkong"), "regular")
            assert upload(archive, key, "rightthesis-backup-jude-2026", "cn-hongkong") == (
                "rightthesis-backups/" + archive.name
            )
            assert calls == [("rightthesis-backups/" + archive.name, str(archive))]
            tampered = archive_dir / "rightthesis-tampered.rtbk"
            data = bytearray(archive.read_bytes())
            data[-18] ^= 1
            tampered.write_bytes(data)
            try:
                upload(tampered, key, "rightthesis-backup-jude-2026", "cn-hongkong")
            except Exception:
                pass
            else:
                raise AssertionError("tampered archive uploaded")
            assert len(calls) == 1


if __name__ == "__main__":
    test_upload_only_verified_encrypted_archive()
    print("✓ OSS 上传仅接受新近且已校验的加密备份")

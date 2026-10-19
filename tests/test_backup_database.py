"""Encrypted SQLite backup/restore regression checks (no production data)."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from backup_database import backup, init_key, restore, verify  # noqa: E402


def test_backup_roundtrip_and_corruption():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        database = root / "live.sqlite3"
        with sqlite3.connect(database) as connection:
            for table in ("accounts", "manuscripts", "rewrite_jobs", "orders", "ledger_entries"):
                connection.execute(f"CREATE TABLE {table} (value TEXT)")
            connection.execute("INSERT INTO manuscripts VALUES (?)", ("private thesis draft",))
        key = root / "keys" / "backup.key"
        init_key(key)
        assert key.stat().st_mode & 0o077 == 0
        try:
            init_key(key)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing backup key must not be overwritten")
        archive = backup(database, root / "archives", key)
        assert b"private thesis draft" not in archive.read_bytes()
        verify(archive, key)
        restored = root / "restored.sqlite3"
        restore(archive, restored, key)
        assert not list(root.glob("restored.sqlite3.part-*"))
        with sqlite3.connect(restored) as connection:
            assert connection.execute("SELECT value FROM manuscripts").fetchone() == (
                "private thesis draft",)
        try:
            restore(archive, restored, key)
        except ValueError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("restore must not overwrite a database")
        corrupted = root / "archives" / "corrupted.rtbk"
        data = bytearray(archive.read_bytes())
        data[-18] ^= 1
        corrupted.write_bytes(data)
        try:
            verify(corrupted, key)
        except Exception:
            pass
        else:
            raise AssertionError("tampered archive must fail authentication")


if __name__ == "__main__":
    test_backup_roundtrip_and_corruption()
    print("✓ 加密备份、校验、还原及篡改拒绝")

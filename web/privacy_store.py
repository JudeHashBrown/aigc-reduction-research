"""Account data export and reviewable deletion requests.

Financial records are intentionally retained under a pseudonymous account ID
after a deletion request is fulfilled. An operator must verify a restorable
backup and settle any remaining paid entitlement before removing identity and
manuscript data.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path


class PrivacyError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class PrivacyStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._init_schema()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def _init_schema(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS privacy_requests (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    email TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind='account_deletion'),
                    status TEXT NOT NULL CHECK(status IN ('pending','cancelled','completed')),
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_privacy_requests_account
                    ON privacy_requests(account_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_privacy_requests_status
                    ON privacy_requests(status, created_at);
            """)

    @staticmethod
    def _rows(db, table: str, account_id: str):
        return [dict(row) for row in db.execute(
            f"SELECT * FROM {table} WHERE account_id=?", (account_id,)
        )]

    def export(self, account_id: str) -> dict:
        with self._connect() as db:
            db.execute("BEGIN")
            profile = db.execute(
                "SELECT * FROM auth_profiles WHERE account_id=?", (account_id,)
            ).fetchone()
            if not profile:
                raise PrivacyError("账户不存在或已删除。", 404)
            result = {
                "format": "rightthesis-account-export-v1",
                "exported_at": int(time.time()),
                "account_id": account_id,
                "profile": dict(profile),
                "verified_emails": self._rows(db, "auth_verified_emails", account_id),
                "identities": self._rows(db, "auth_identities", account_id),
                "manuscripts": self._rows(db, "manuscripts", account_id),
                "manuscript_versions": self._rows(db, "manuscript_versions", account_id),
                "rewrite_jobs": self._rows(db, "rewrite_jobs", account_id),
                "orders": self._rows(db, "orders", account_id),
                "credit_grants": self._rows(db, "credit_grants", account_id),
                "usage_reservations": self._rows(db, "usage_reservations", account_id),
                "ledger_entries": self._rows(db, "ledger_entries", account_id),
                "privacy_requests": self._rows(db, "privacy_requests", account_id),
            }
            jobs = {row["job_id"] for row in result["usage_reservations"]}
            result["usage_allocations"] = [dict(row) for row in db.execute(
                "SELECT * FROM usage_allocations WHERE job_id IN ("
                + ",".join("?" for _ in jobs) + ")", tuple(jobs)
            )] if jobs else []
            db.commit()
            # Authentication secrets, password hashes, session tokens, email
            # verification codes and provider webhook payloads are omitted.
            return result

    def current_request(self, account_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT id,kind,status,created_at,updated_at
                   FROM privacy_requests WHERE account_id=?
                   ORDER BY created_at DESC,rowid DESC LIMIT 1""", (account_id,)
            ).fetchone()
            return dict(row) if row else None

    def request_deletion(self, account_id: str, confirmed_email: str) -> dict:
        now = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            profile = db.execute(
                "SELECT primary_email FROM auth_profiles WHERE account_id=?", (account_id,)
            ).fetchone()
            if not profile or confirmed_email != profile["primary_email"]:
                raise PrivacyError("请输入当前账户的完整邮箱地址以确认。", 400)
            existing = db.execute(
                """SELECT id,kind,status,created_at,updated_at
                   FROM privacy_requests WHERE account_id=? AND status='pending'
                   ORDER BY created_at DESC LIMIT 1""", (account_id,)
            ).fetchone()
            if existing:
                return dict(existing)
            request_id = "pr_" + secrets.token_hex(12)
            db.execute(
                """INSERT INTO privacy_requests
                   (id,account_id,email,kind,status,created_at,updated_at)
                   VALUES(?,?,?,'account_deletion','pending',?,?)""",
                (request_id, account_id, profile["primary_email"], now, now),
            )
            return {"id": request_id, "kind": "account_deletion", "status": "pending",
                    "created_at": now, "updated_at": now}

    def cancel_deletion(self, account_id: str) -> dict | None:
        now = int(time.time())
        with self._connect() as db:
            db.execute(
                """UPDATE privacy_requests SET status='cancelled',updated_at=?
                   WHERE account_id=? AND status='pending'""", (now, account_id)
            )
        return self.current_request(account_id)

    def pending_requests(self) -> list[dict]:
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT id,account_id,email,kind,status,created_at
                   FROM privacy_requests WHERE status='pending' ORDER BY created_at"""
            )]

    def complete_deletion(self, request_id: str) -> dict:
        """Fulfill one request after backup verification and financial review."""
        now = int(time.time())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            request = db.execute(
                "SELECT * FROM privacy_requests WHERE id=? AND status='pending'",
                (request_id,),
            ).fetchone()
            if not request:
                raise PrivacyError("没有待处理的删除请求。", 404)
            account_id = request["account_id"]
            running = db.execute(
                "SELECT COUNT(*) FROM rewrite_jobs WHERE account_id=? AND state='running'",
                (account_id,),
            ).fetchone()[0]
            pending = db.execute(
                """SELECT COUNT(*) FROM orders WHERE account_id=?
                   AND status='pending'""", (account_id,)
            ).fetchone()[0]
            paid_balance = db.execute(
                """SELECT COALESCE(SUM(remaining),0) FROM credit_grants
                   WHERE account_id=? AND kind!='welcome' AND revoked_at IS NULL
                     AND (expires_at IS NULL OR expires_at>?)""",
                (account_id, now),
            ).fetchone()[0]
            if running or pending or paid_balance:
                raise PrivacyError(
                    "仍有运行任务、待确认付款或未用付费额度；先处理这些权益后再删除。", 409
                )
            session_hashes = [row[0] for row in db.execute(
                "SELECT token_hash FROM auth_sessions WHERE account_id=?", (account_id,)
            )]
            if session_hashes:
                placeholders = ",".join("?" for _ in session_hashes)
                db.execute(f"DELETE FROM auth_oauth_flows WHERE session_hash IN ({placeholders})",
                           session_hashes)
                db.execute(f"DELETE FROM auth_email_challenges WHERE session_hash IN ({placeholders})",
                           session_hashes)
            db.execute("DELETE FROM manuscript_versions WHERE account_id=?", (account_id,))
            db.execute("DELETE FROM manuscripts WHERE account_id=?", (account_id,))
            db.execute("DELETE FROM rewrite_jobs WHERE account_id=?", (account_id,))
            db.execute("DELETE FROM auth_password_credentials WHERE account_id=?", (account_id,))
            db.execute("DELETE FROM auth_identities WHERE account_id=?", (account_id,))
            db.execute("DELETE FROM auth_verified_emails WHERE account_id=?", (account_id,))
            db.execute("DELETE FROM auth_sessions WHERE account_id=?", (account_id,))
            db.execute("DELETE FROM auth_profiles WHERE account_id=?", (account_id,))
            db.execute("UPDATE privacy_requests SET email='' WHERE account_id=?",
                       (account_id,))
            db.execute(
                """UPDATE privacy_requests SET status='completed',updated_at=?
                   WHERE id=?""", (now, request_id)
            )
            return {"request_id": request_id, "account_id": account_id,
                    "status": "completed"}

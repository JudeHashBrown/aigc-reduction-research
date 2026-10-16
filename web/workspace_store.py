"""Durable, account-scoped manuscripts and rewrite jobs for the local service."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class WorkspaceStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS manuscripts (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    current TEXT NOT NULL,
                    report_json TEXT,
                    document_json TEXT,
                    notices_json TEXT NOT NULL,
                    last_job_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS manuscripts_owner_updated
                    ON manuscripts(account_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS rewrite_jobs (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    done INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    result_json TEXT,
                    error TEXT,
                    billing_json TEXT,
                    manuscript_id TEXT,
                    owner_pid INTEGER,
                    t0 REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS rewrite_jobs_owner_updated
                    ON rewrite_jobs(account_id, updated_at DESC);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(rewrite_jobs)")}
            if "owner_pid" not in columns:
                db.execute("ALTER TABLE rewrite_jobs ADD COLUMN owner_pid INTEGER")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @staticmethod
    def _manuscript(row):
        if row is None:
            return None
        value = dict(row)
        return {
            "id": value["id"], "revision": value["revision"],
            "name": value["name"], "kind": value["kind"],
            "source": value["source"], "current": value["current"],
            "report": json.loads(value["report_json"]) if value["report_json"] else None,
            "document": json.loads(value["document_json"]) if value["document_json"] else None,
            "notices": json.loads(value["notices_json"]),
            "last_job_id": value["last_job_id"],
            "created_at": value["created_at"], "updated_at": value["updated_at"],
        }

    def create_manuscript(self, account_id, value):
        now = time.time()
        manuscript_id = "doc_" + secrets.token_hex(12)
        with self._connect() as db:
            db.execute("""INSERT INTO manuscripts
                (id, account_id, name, kind, source, current, report_json,
                 document_json, notices_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (manuscript_id, account_id, value["name"], value["kind"],
                 value["source"], value["current"], _json(value.get("report")),
                 _json(value.get("document")), _json(value.get("notices", [])), now, now))
        return self.get_manuscript(account_id, manuscript_id)

    def get_manuscript(self, account_id, manuscript_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM manuscripts WHERE id=? AND account_id=?",
                             (manuscript_id, account_id)).fetchone()
        return self._manuscript(row)

    def list_manuscripts(self, account_id):
        with self._connect() as db:
            rows = db.execute("""SELECT id, revision, name, kind, length(source) AS source_chars,
                length(current) AS current_chars, last_job_id, created_at, updated_at
                FROM manuscripts WHERE account_id=? ORDER BY updated_at DESC""",
                (account_id,)).fetchall()
        return [dict(row) for row in rows]

    def update_manuscript(self, account_id, manuscript_id, revision, value):
        now = time.time()
        with self._connect() as db:
            cursor = db.execute("""UPDATE manuscripts SET revision=revision+1,
                current=?, report_json=?, notices_json=?, updated_at=?
                WHERE id=? AND account_id=? AND revision=?""",
                (value["current"], _json(value.get("report")),
                 _json(value.get("notices", [])), now,
                 manuscript_id, account_id, revision))
            if cursor.rowcount != 1:
                exists = db.execute("SELECT 1 FROM manuscripts WHERE id=? AND account_id=?",
                                    (manuscript_id, account_id)).fetchone()
                return "conflict" if exists else "missing", None
        return "saved", self.get_manuscript(account_id, manuscript_id)

    def mark_last_job(self, account_id, manuscript_id, job_id):
        with self._connect() as db:
            db.execute("""UPDATE manuscripts SET last_job_id=?
                WHERE id=? AND account_id=?""", (job_id, manuscript_id, account_id))

    @staticmethod
    def _job(row):
        if row is None:
            return None
        value = dict(row)
        value["result"] = json.loads(value.pop("result_json")) if value["result_json"] else None
        value["billing"] = json.loads(value.pop("billing_json")) if value["billing_json"] else None
        return value

    def get_job(self, account_id, job_id):
        with self._connect() as db:
            row = db.execute("SELECT * FROM rewrite_jobs WHERE id=? AND account_id=?",
                             (job_id, account_id)).fetchone()
        return self._job(row)

    def claim_job(self, account_id, request_id, request_hash, job_id, max_active,
                  manuscript_id=None):
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM rewrite_jobs WHERE id=?", (job_id,)).fetchone()
            if existing:
                job = self._job(existing)
                return ("reused" if job["account_id"] == account_id
                        and job["request_hash"] == request_hash else "conflict"), job
            active = db.execute("SELECT count(*) FROM rewrite_jobs WHERE state='running'").fetchone()[0]
            if active >= max_active:
                return "busy", None
            db.execute("""INSERT INTO rewrite_jobs
                (id, account_id, request_id, request_hash, state, phase,
                 manuscript_id, owner_pid, t0, updated_at)
                VALUES (?, ?, ?, ?, 'running', 'preparing', ?, ?, ?, ?)""",
                (job_id, account_id, request_id, request_hash, manuscript_id,
                 os.getpid(), now, now))
        return "created", self.get_job(account_id, job_id)

    def update_job(self, job_id, **changes):
        columns = {
            "done", "total", "state", "phase", "error", "manuscript_id",
        }
        values = {}
        for key, value in changes.items():
            if key in columns:
                values[key] = value
            elif key in {"result", "billing"}:
                values[key + "_json"] = _json(value)
        if not values:
            return
        values["updated_at"] = time.time()
        with self._connect() as db:
            db.execute("UPDATE rewrite_jobs SET " + ", ".join(f"{key}=?" for key in values)
                       + " WHERE id=?", (*values.values(), job_id))

    def running_jobs(self):
        with self._connect() as db:
            rows = db.execute("SELECT * FROM rewrite_jobs WHERE state='running'").fetchall()
        return [self._job(row) for row in rows]

    def list_jobs(self, account_id):
        with self._connect() as db:
            rows = db.execute("""SELECT id, state, phase, done, total, error, manuscript_id,
                t0, updated_at FROM rewrite_jobs WHERE account_id=?
                ORDER BY t0 DESC""", (account_id,)).fetchall()
        return [dict(row) for row in rows]

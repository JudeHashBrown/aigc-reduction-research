"""Bounded, read-only operational views; never return manuscript or job text."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class AdminStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=30000")
        return db

    def users(self, limit: int = 100):
        with self._connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT a.id AS account_id, p.primary_email, p.display_name,
                       a.created_at, COUNT(DISTINCT m.id) AS manuscript_count,
                       COALESCE((SELECT SUM(g.remaining) FROM credit_grants g
                         WHERE g.account_id=a.id AND g.revoked_at IS NULL
                           AND (g.expires_at IS NULL OR g.expires_at>?)), 0) AS balance
                FROM accounts a
                JOIN auth_profiles p ON p.account_id=a.id
                LEFT JOIN manuscripts m ON m.account_id=a.id
                GROUP BY a.id ORDER BY a.created_at DESC LIMIT ?
            """, (int(time.time()), min(max(limit, 1), 100))).fetchall()]

    def jobs(self, limit: int = 100):
        with self._connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT j.id, j.account_id, j.manuscript_id, j.state, j.phase,
                       j.done, j.total, j.t0, j.updated_at,
                       u.billable_chars, u.input_tokens, u.output_tokens,
                       u.status AS billing_status
                FROM rewrite_jobs j LEFT JOIN usage_reservations u ON u.job_id=j.id
                ORDER BY j.t0 DESC LIMIT ?
            """, (min(max(limit, 1), 100),)).fetchall()]

    def economics(self):
        with self._connect() as db:
            order = db.execute("""SELECT COUNT(*) AS paid_orders,
                    COALESCE(SUM(amount_fen-refunded_fen),0) AS net_sales_fen
                FROM orders WHERE status IN ('paid','partially_refunded','refunded')
                  AND currency='CNY'""").fetchone()
            usage = db.execute("""SELECT COUNT(*) AS settled_jobs,
                    COALESCE(SUM(input_tokens),0) AS input_tokens,
                    COALESCE(SUM(output_tokens),0) AS output_tokens
                FROM usage_reservations WHERE status='committed'""").fetchone()
            return {**dict(order), **dict(usage), "currency": "CNY",
                    "model_cost_available": False}

    def service(self):
        with self._connect() as db:
            now = int(time.time())
            jobs = db.execute("""SELECT state, COUNT(*) AS count FROM rewrite_jobs
                GROUP BY state""").fetchall()
            pending = db.execute("""SELECT COUNT(*) FROM orders
                WHERE status='pending' AND NOT (provider='stripe' AND (
                  (checkout_expires_at IS NOT NULL AND checkout_expires_at<=?)
                  OR (provider_order_id IS NULL AND checkout_url IS NULL
                      AND created_at<=?)))""", (now, now - 30 * 60)).fetchone()[0]
            return {"jobs_by_state": {row["state"]: row["count"] for row in jobs},
                    "pending_orders": pending, "checked_at": now,
                    "controls_available": False}

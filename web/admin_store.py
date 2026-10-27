"""Bounded, read-only operational views; never return manuscript or job text."""
from __future__ import annotations

import json
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
        """Compatibility view for the original read-only operator summary."""
        return self.search_users(limit=limit)["users"]

    def search_users(self, query: str = "", limit: int = 20, offset: int = 0):
        query = str(query or "").strip()[:120]
        limit = min(max(int(limit), 1), 100)
        offset = min(max(int(offset), 0), 100_000)
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        where = """WHERE (?='' OR p.primary_email LIKE ? ESCAPE '\\'
                    OR p.display_name LIKE ? ESCAPE '\\'
                    OR a.id LIKE ? ESCAPE '\\')"""
        params = (query, pattern, pattern, pattern)
        with self._connect() as db:
            total = db.execute(
                f"SELECT COUNT(*) FROM accounts a JOIN auth_profiles p ON p.account_id=a.id {where}",
                params,
            ).fetchone()[0]
            users = [dict(row) for row in db.execute(f"""
                SELECT a.id AS account_id, p.primary_email, p.display_name,
                       a.created_at,
                       (SELECT COUNT(*) FROM manuscripts m WHERE m.account_id=a.id)
                         AS manuscript_count,
                       COALESCE((SELECT SUM(g.remaining) FROM credit_grants g
                         WHERE g.account_id=a.id AND g.revoked_at IS NULL
                           AND (g.expires_at IS NULL OR g.expires_at>?)), 0) AS balance
                FROM accounts a
                JOIN auth_profiles p ON p.account_id=a.id
                {where}
                ORDER BY a.created_at DESC,a.id DESC LIMIT ? OFFSET ?
            """, (int(time.time()), *params, limit, offset)).fetchall()]
            return {"users": users, "total": total, "limit": limit, "offset": offset}

    def user_detail(self, account_id: str) -> dict | None:
        """Identity, entitlement and payment metadata only; never manuscript text."""
        with self._connect() as db:
            row = db.execute("""SELECT a.id AS account_id,p.primary_email,p.display_name,
                       a.created_at,
                       (SELECT COUNT(*) FROM manuscripts m WHERE m.account_id=a.id)
                         AS manuscript_count,
                       (SELECT COUNT(*) FROM auth_sessions s WHERE s.account_id=a.id
                         AND s.authenticated=1 AND s.revoked_at IS NULL AND s.expires_at>?)
                         AS active_sessions,
                       COALESCE((SELECT SUM(g.remaining) FROM credit_grants g
                         WHERE g.account_id=a.id AND g.revoked_at IS NULL
                           AND (g.expires_at IS NULL OR g.expires_at>?)),0) AS balance
                   FROM accounts a JOIN auth_profiles p ON p.account_id=a.id
                   WHERE a.id=?""", (int(time.time()), int(time.time()), account_id)).fetchone()
            if not row:
                return None
            grants = [dict(item) for item in db.execute("""SELECT id,kind,product_id,
                       remaining,granted,expires_at,created_at
                   FROM credit_grants WHERE account_id=? AND revoked_at IS NULL
                   ORDER BY created_at DESC LIMIT 30""", (account_id,)).fetchall()]
            orders = [dict(item) for item in db.execute("""SELECT id,product_id,status,
                       amount_fen,currency,refunded_fen,created_at,paid_at,
                       product_snapshot_json
                   FROM orders WHERE account_id=? ORDER BY created_at DESC LIMIT 20""",
                   (account_id,)).fetchall()]
            for order in orders:
                try:
                    snapshot = json.loads(order.pop("product_snapshot_json") or "null")
                except (TypeError, ValueError):
                    snapshot = None
                order["metering_version"] = (snapshot.get("metering_version", 1)
                                              if isinstance(snapshot, dict) else 1)
            admin_grants = [dict(item) for item in db.execute("""SELECT a.request_id,
                       a.actor_account_id,a.credits,a.valid_days,a.reason,a.created_at,
                       p.primary_email AS actor_email,g.expires_at
                   FROM admin_credit_grants a
                   JOIN credit_grants g ON g.id=a.grant_id
                   LEFT JOIN auth_profiles p ON p.account_id=a.actor_account_id
                   WHERE a.target_account_id=?
                   ORDER BY a.created_at DESC,a.request_id DESC LIMIT 20""",
                   (account_id,)).fetchall()]
            return {**dict(row), "providers": [item[0] for item in db.execute(
                    "SELECT provider FROM auth_identities WHERE account_id=? ORDER BY provider",
                    (account_id,)).fetchall()],
                "grants": grants, "orders": orders, "admin_grants": admin_grants}

    def jobs(self, limit: int = 100):
        with self._connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT j.id, j.account_id, j.manuscript_id, j.state, j.phase,
                       j.done, j.total, j.t0, j.updated_at,
                       u.billable_chars, u.metering_version,
                       u.input_tokens, u.output_tokens,
                       u.status AS billing_status
                FROM rewrite_jobs j LEFT JOIN usage_reservations u ON u.job_id=j.id
                ORDER BY j.t0 DESC LIMIT ?
            """, (min(max(limit, 1), 100),)).fetchall()]

    def economics(self):
        with self._connect() as db:
            sales_rows = [dict(row) for row in db.execute("""
                SELECT currency, COUNT(*) AS paid_orders,
                       COALESCE(SUM(amount_fen-refunded_fen),0) AS net_sales_minor
                FROM orders
                WHERE status IN ('paid','partially_refunded','refunded')
                  AND provider='stripe' AND stripe_livemode=1
                GROUP BY currency ORDER BY currency
            """).fetchall()]
            # Keep the old CNY-only fields for older clients. Adding a USD
            # price must never silently sum USD cents with CNY fen.
            cny = next((row for row in sales_rows if row["currency"] == "CNY"), None)
            usage = db.execute("""SELECT COUNT(*) AS settled_jobs,
                    COALESCE(SUM(input_tokens),0) AS input_tokens,
                    COALESCE(SUM(output_tokens),0) AS output_tokens
                FROM usage_reservations WHERE status='committed'""").fetchone()
            return {"paid_orders": cny["paid_orders"] if cny else 0,
                    "net_sales_fen": cny["net_sales_minor"] if cny else 0,
                    "sales_by_currency": sales_rows,
                    **dict(usage), "currency": "CNY",
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

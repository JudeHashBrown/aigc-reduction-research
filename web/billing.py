"""Local-MVP billing and entitlement ledger.

The editing engine stays payment-agnostic.  This module owns the server-side
product catalog, immutable orders, expiring credit grants, and atomic usage
reservations.  It deliberately supports only a clearly-labelled mock checkout
for now: real Stripe / epay callbacks require an authenticated public control
plane and provider-specific signature verification.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, List, Optional


WELCOME_CREDITS = 800
WELCOME_MAX_CHARS = 800
STRENGTH_MULTIPLIER_MILLI = {
    "conservative": 1000,
    "balanced": 1000,
    "deep": 1500,
}


PRODUCTS: Dict[str, Dict] = {
    "pack_3k": {
        "id": "pack_3k", "name": "小字数包", "kind": "pack",
        "price_fen": 990, "currency": "CNY", "credits": 3000,
        "max_chars_per_job": 3000, "valid_days": 90,
        "description": "适合章节或短稿，不自动续费。",
    },
    "pack_10k": {
        "id": "pack_10k", "name": "论文包", "kind": "pack",
        "price_fen": 2990, "currency": "CNY", "credits": 10000,
        "max_chars_per_job": 10000, "valid_days": 90,
        "description": "适合一篇短论文或多轮局部修改。",
    },
    "pack_30k": {
        "id": "pack_30k", "name": "大论文包", "kind": "pack",
        "price_fen": 6990, "currency": "CNY", "credits": 30000,
        "max_chars_per_job": 30000, "valid_days": 90,
        "description": "适合长论文，支持异步分块处理。",
    },
    "student_month": {
        "id": "student_month", "name": "学生月卡", "kind": "subscription",
        "price_fen": 3990, "currency": "CNY", "credits": 20000,
        "max_chars_per_job": 10000, "valid_days": 30,
        "description": "一次购买，30 天有效，20,000 字；不自动续费。",
    },
    "pro_month": {
        "id": "pro_month", "name": "高频月卡", "kind": "subscription",
        "price_fen": 7990, "currency": "CNY", "credits": 60000,
        "max_chars_per_job": 30000, "valid_days": 30,
        "description": "一次购买，30 天有效，60,000 字；不自动续费。",
    },
}


class BillingError(RuntimeError):
    def __init__(self, message: str, status: int = 400, details: Optional[Dict] = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}


def billable_chars(text: str) -> int:
    """Count normalized, non-whitespace Unicode code points.

    The server normalizes text before calling this function.  Keeping the
    contract here makes browser display, entitlement checks and the ledger use
    one definition instead of mixing ``len`` with a regular-expression count.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return sum(1 for char in text if not char.isspace())


def request_fingerprint(text: str, strength: str) -> str:
    return hashlib.sha256((strength + "\0" + text).encode("utf-8")).hexdigest()


class BillingStore:
    def __init__(self, path: Path | str, now: Optional[Callable[[], float]] = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now or time.time
        self._schema_lock = threading.Lock()
        self._init_schema()
        # A reserved job cannot still be running after a process restart.  Only
        # stale reservations are released; live-process jobs finalize normally.
        self.release_stale(max_age_seconds=2 * 60 * 60)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        with self._schema_lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS accounts (
                        id TEXT PRIMARY KEY,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS orders (
                        id TEXT PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id),
                        product_id TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        provider_order_id TEXT,
                        idempotency_key TEXT NOT NULL,
                        status TEXT NOT NULL,
                        amount_fen INTEGER NOT NULL CHECK(amount_fen >= 0),
                        currency TEXT NOT NULL,
                        credits INTEGER NOT NULL CHECK(credits >= 0),
                        created_at INTEGER NOT NULL,
                        paid_at INTEGER,
                        checkout_url TEXT,
                        checkout_expires_at INTEGER,
                        product_snapshot_json TEXT,
                        stripe_livemode INTEGER NOT NULL DEFAULT 0,
                        payment_intent_id TEXT,
                        refunded_fen INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(account_id, idempotency_key),
                        UNIQUE(provider, provider_order_id)
                    );
                    CREATE TABLE IF NOT EXISTS payment_events (
                        provider TEXT NOT NULL,
                        event_id TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        processed_at INTEGER NOT NULL,
                        PRIMARY KEY(provider, event_id)
                    );
                    CREATE TABLE IF NOT EXISTS stripe_refunds (
                        refund_id TEXT PRIMARY KEY,
                        payment_intent_id TEXT NOT NULL,
                        event_id TEXT NOT NULL,
                        amount_fen INTEGER NOT NULL,
                        currency TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        applied_at INTEGER
                    );
                    CREATE INDEX IF NOT EXISTS idx_stripe_refunds_payment_intent
                        ON stripe_refunds(payment_intent_id);
                    CREATE TABLE IF NOT EXISTS credit_grants (
                        id TEXT PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id),
                        kind TEXT NOT NULL,
                        product_id TEXT NOT NULL,
                        granted INTEGER NOT NULL CHECK(granted >= 0),
                        remaining INTEGER NOT NULL CHECK(remaining >= 0),
                        max_chars_per_job INTEGER NOT NULL CHECK(max_chars_per_job >= 0),
                        expires_at INTEGER,
                        reference TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        revoked_at INTEGER,
                        refunded_credits INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(account_id, reference)
                    );
                    CREATE TABLE IF NOT EXISTS usage_reservations (
                        job_id TEXT PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id),
                        request_hash TEXT NOT NULL,
                        strength TEXT NOT NULL,
                        billable_chars INTEGER NOT NULL CHECK(billable_chars >= 0),
                        multiplier_milli INTEGER NOT NULL CHECK(multiplier_milli >= 1000),
                        reserved INTEGER NOT NULL CHECK(reserved >= 0),
                        status TEXT NOT NULL,
                        input_tokens INTEGER NOT NULL DEFAULT 0,
                        output_tokens INTEGER NOT NULL DEFAULT 0,
                        created_at INTEGER NOT NULL,
                        finalized_at INTEGER
                    );
                    CREATE TABLE IF NOT EXISTS usage_allocations (
                        job_id TEXT NOT NULL REFERENCES usage_reservations(job_id),
                        grant_id TEXT NOT NULL REFERENCES credit_grants(id),
                        amount INTEGER NOT NULL CHECK(amount > 0),
                        PRIMARY KEY(job_id, grant_id)
                    );
                    CREATE TABLE IF NOT EXISTS ledger_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id TEXT NOT NULL REFERENCES accounts(id),
                        delta INTEGER NOT NULL,
                        kind TEXT NOT NULL,
                        reference TEXT NOT NULL,
                        balance_after INTEGER NOT NULL CHECK(balance_after >= 0),
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        created_at INTEGER NOT NULL,
                        UNIQUE(account_id, kind, reference)
                    );
                    CREATE INDEX IF NOT EXISTS idx_grants_account_expiry
                        ON credit_grants(account_id, expires_at, created_at);
                    CREATE INDEX IF NOT EXISTS idx_ledger_account_created
                        ON ledger_entries(account_id, created_at DESC, id DESC);
                """)
                # Existing local ledgers predate Stripe. Keep their orders and
                # grants intact while adding the checkout snapshot fields.
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
                for name, declaration in (
                    ("checkout_url", "TEXT"),
                    ("checkout_expires_at", "INTEGER"),
                    ("product_snapshot_json", "TEXT"),
                    ("stripe_livemode", "INTEGER NOT NULL DEFAULT 0"),
                    ("payment_intent_id", "TEXT"),
                    ("refunded_fen", "INTEGER NOT NULL DEFAULT 0"),
                ):
                    if name not in columns:
                        conn.execute(f"ALTER TABLE orders ADD COLUMN {name} {declaration}")
                grant_columns = {row["name"] for row in conn.execute("PRAGMA table_info(credit_grants)")}
                if "revoked_at" not in grant_columns:
                    conn.execute("ALTER TABLE credit_grants ADD COLUMN revoked_at INTEGER")
                if "refunded_credits" not in grant_columns:
                    conn.execute("ALTER TABLE credit_grants ADD COLUMN refunded_credits INTEGER NOT NULL DEFAULT 0")
                # Older releases already revoked full-refund grants but did
                # not store a cumulative amount. Mark those orders as applied
                # so a later refund.updated webhook cannot insert a second
                # ledger reversal for the same purchase.
                conn.execute(
                    "UPDATE orders SET refunded_fen=amount_fen "
                    "WHERE provider='stripe' AND status='refunded' AND refunded_fen=0"
                )
                conn.execute(
                    """UPDATE credit_grants SET refunded_credits=granted
                       WHERE refunded_credits=0 AND revoked_at IS NOT NULL
                         AND reference IN (
                           SELECT 'order:' || id FROM orders
                           WHERE provider='stripe' AND status='refunded')"""
                )
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_stripe_payment_intent "
                             "ON orders(payment_intent_id) WHERE payment_intent_id IS NOT NULL")
            finally:
                conn.close()

    @staticmethod
    def public_catalog() -> List[Dict]:
        free = {
            "id": "free", "name": "免费体验", "kind": "free",
            "price_fen": 0, "currency": "CNY", "credits": WELCOME_CREDITS,
            "max_chars_per_job": WELCOME_MAX_CHARS, "valid_days": None,
            "description": "中英文规则分析免费；首次保守改写 800 字。",
        }
        return [free] + [dict(product) for product in PRODUCTS.values()]

    def _ensure_account(self, conn: sqlite3.Connection, account_id: str, now: int):
        conn.execute(
            "INSERT OR IGNORE INTO accounts(id, created_at, updated_at) VALUES(?,?,?)",
            (account_id, now, now),
        )
        reference = "welcome:v1"
        grant = conn.execute(
            "SELECT id FROM credit_grants WHERE account_id=? AND reference=?",
            (account_id, reference),
        ).fetchone()
        if grant:
            return
        grant_id = "gr_" + uuid.uuid4().hex
        conn.execute(
            """INSERT INTO credit_grants
               (id,account_id,kind,product_id,granted,remaining,max_chars_per_job,
                expires_at,reference,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (grant_id, account_id, "welcome", "free", WELCOME_CREDITS,
             WELCOME_CREDITS, WELCOME_MAX_CHARS, None, reference, now),
        )
        conn.execute(
            """INSERT OR IGNORE INTO ledger_entries
               (account_id,delta,kind,reference,balance_after,metadata_json,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (account_id, WELCOME_CREDITS, "grant", reference, WELCOME_CREDITS,
             json.dumps({"product_id": "free"}, ensure_ascii=False), now),
        )

    @staticmethod
    def _active_grants(conn: sqlite3.Connection, account_id: str, now: int):
        return conn.execute(
            """SELECT * FROM credit_grants
               WHERE account_id=? AND remaining>0
                 AND revoked_at IS NULL
                 AND (expires_at IS NULL OR expires_at>?)
               ORDER BY CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END,
                        expires_at ASC, created_at ASC, id ASC""",
            (account_id, now),
        ).fetchall()

    @staticmethod
    def _active_balance(conn: sqlite3.Connection, account_id: str, now: int) -> int:
        row = conn.execute(
            """SELECT COALESCE(SUM(remaining),0) AS balance FROM credit_grants
               WHERE account_id=? AND remaining>0
                 AND revoked_at IS NULL
                 AND (expires_at IS NULL OR expires_at>?)""",
            (account_id, now),
        ).fetchone()
        return int(row["balance"])

    def summary(self, account_id: str) -> Dict:
        now = int(self._now())
        with self._transaction() as conn:
            self._ensure_account(conn, account_id, now)
            grants = self._active_grants(conn, account_id, now)
            balance = sum(int(row["remaining"]) for row in grants)
        paid = [row for row in grants if row["kind"] != "welcome"]
        priorities = {"pro_month": 50, "student_month": 40,
                      "pack_30k": 30, "pack_10k": 20, "pack_3k": 10,
                      "trial": 5, "free": 0}
        plan_id = max((row["product_id"] for row in paid),
                      key=lambda value: priorities.get(value, 1), default="free")
        plan = PRODUCTS.get(plan_id, {"name": "内测体验" if plan_id == "trial"
                                          else "免费体验"})
        max_chars = max((int(row["max_chars_per_job"]) for row in grants), default=0)
        return {
            "account_id": account_id,
            "plan_id": plan_id,
            "plan_name": plan["name"],
            "balance": balance,
            "max_chars_per_job": max_chars,
            "allowed_strengths": (["conservative", "balanced", "deep"]
                                  if paid else ["conservative"]),
            "grants": [
                {
                    "product_id": row["product_id"],
                    "kind": row["kind"],
                    "remaining": int(row["remaining"]),
                    "expires_at": row["expires_at"],
                }
                for row in grants
            ],
        }

    def grant_trial(self, account_id: str, target_credits: int = 3000,
                    max_chars_per_job: int = 3000) -> Dict:
        """Idempotently raise an anonymous account to a target trial balance.

        ``target_credits`` includes the normal welcome grant.  With the
        defaults this adds a 2,200-character ``trial:v1`` bonus after the
        existing 800-character welcome grant, for 3,000 total.  Repeated
        login/summary calls never mint another bonus.
        """
        try:
            target_credits = int(target_credits)
            max_chars_per_job = int(max_chars_per_job)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("trial credits and max chars must be integers") from exc
        if target_credits < 0 or max_chars_per_job < 1:
            raise ValueError("trial credits must be >= 0 and max chars must be >= 1")
        bonus = max(0, target_credits - WELCOME_CREDITS)
        now = int(self._now())
        reference = "trial:v1"
        with self._transaction() as conn:
            self._ensure_account(conn, account_id, now)
            existing = conn.execute(
                "SELECT id FROM credit_grants WHERE account_id=? AND reference=?",
                (account_id, reference),
            ).fetchone()
            if not existing:
                balance_before = self._active_balance(conn, account_id, now)
                grant_id = "gr_" + uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO credit_grants
                       (id,account_id,kind,product_id,granted,remaining,
                        max_chars_per_job,expires_at,reference,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (grant_id, account_id, "trial", "trial", bonus, bonus,
                     max_chars_per_job, None, reference, now),
                )
                conn.execute(
                    """INSERT INTO ledger_entries
                       (account_id,delta,kind,reference,balance_after,
                        metadata_json,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (account_id, bonus, "grant", reference,
                     balance_before + bonus,
                     json.dumps({"product_id": "trial",
                                 "target_credits": target_credits},
                                ensure_ascii=False), now),
                )
        return self.summary(account_id)

    def ledger(self, account_id: str, limit: int = 30) -> List[Dict]:
        limit = max(1, min(int(limit), 100))
        now = int(self._now())
        with self._transaction() as conn:
            self._ensure_account(conn, account_id, now)
            rows = conn.execute(
                """SELECT delta,kind,reference,balance_after,metadata_json,created_at
                   FROM ledger_entries WHERE account_id=?
                   ORDER BY created_at DESC,id DESC LIMIT ?""",
                (account_id, limit),
            ).fetchall()
        return [
            {
                "delta": int(row["delta"]), "kind": row["kind"],
                "reference": row["reference"],
                "balance_after": int(row["balance_after"]),
                "metadata": json.loads(row["metadata_json"] or "{}"),
                "created_at": int(row["created_at"]),
            }
            for row in rows
        ]

    def mock_checkout(self, account_id: str, product_id: str,
                      idempotency_key: str) -> Dict:
        if product_id not in PRODUCTS:
            raise BillingError("未知套餐", 400)
        if not isinstance(idempotency_key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{8,100}", idempotency_key):
            raise BillingError("idempotency_key 格式无效", 400)
        product = PRODUCTS[product_id]
        now = int(self._now())
        reused = False
        with self._transaction() as conn:
            self._ensure_account(conn, account_id, now)
            existing = conn.execute(
                "SELECT * FROM orders WHERE account_id=? AND idempotency_key=?",
                (account_id, idempotency_key),
            ).fetchone()
            if existing:
                if existing["product_id"] != product_id:
                    raise BillingError("同一幂等键不能购买不同套餐", 409)
                order_id = existing["id"]
                reused = True
            else:
                order_id = "ord_" + uuid.uuid4().hex
                conn.execute(
                    """INSERT INTO orders
                       (id,account_id,product_id,provider,provider_order_id,
                        idempotency_key,status,amount_fen,currency,credits,created_at,paid_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (order_id, account_id, product_id, "mock", "mock_" + order_id,
                     idempotency_key, "paid", product["price_fen"], product["currency"],
                     product["credits"], now, now),
                )
                expires_at = now + int(product["valid_days"]) * 86400
                grant_id = "gr_" + uuid.uuid4().hex
                balance_before = self._active_balance(conn, account_id, now)
                conn.execute(
                    """INSERT INTO credit_grants
                       (id,account_id,kind,product_id,granted,remaining,max_chars_per_job,
                        expires_at,reference,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (grant_id, account_id, product["kind"], product_id,
                     product["credits"], product["credits"],
                     product["max_chars_per_job"], expires_at,
                     "order:" + order_id, now),
                )
                conn.execute(
                    """INSERT INTO ledger_entries
                       (account_id,delta,kind,reference,balance_after,metadata_json,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (account_id, product["credits"], "grant", "order:" + order_id,
                     balance_before + product["credits"],
                     json.dumps({"product_id": product_id, "provider": "mock"},
                                ensure_ascii=False), now),
                )
        return {
            "order_id": order_id,
            "status": "paid",
            "provider": "mock",
            "reused": reused,
            "summary": self.summary(account_id),
        }

    def prepare_stripe_checkout(self, account_id: str, product_id: str,
                                idempotency_key: str, livemode: bool = False) -> Dict:
        if product_id not in PRODUCTS:
            raise BillingError("未知套餐", 400)
        if not isinstance(idempotency_key, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{8,100}", idempotency_key):
            raise BillingError("idempotency_key 格式无效", 400)
        now = int(self._now())
        product = dict(PRODUCTS[product_id])
        with self._transaction() as conn:
            self._ensure_account(conn, account_id, now)
            self._expire_pending_checkouts(conn, account_id, now)
            existing = conn.execute(
                "SELECT * FROM orders WHERE account_id=? AND idempotency_key=?",
                (account_id, idempotency_key),
            ).fetchone()
            if existing:
                if (existing["product_id"] != product_id or existing["provider"] != "stripe"
                        or bool(existing["stripe_livemode"]) != livemode):
                    raise BillingError("同一幂等键不能购买不同套餐", 409)
                return dict(existing)
            order_id = "ord_" + uuid.uuid4().hex
            conn.execute(
                """INSERT INTO orders
                   (id,account_id,product_id,provider,provider_order_id,
                    idempotency_key,status,amount_fen,currency,credits,created_at,
                    product_snapshot_json,stripe_livemode)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (order_id, account_id, product_id, "stripe", None,
                 idempotency_key, "pending", product["price_fen"],
                 product["currency"], product["credits"], now,
                 json.dumps(product, ensure_ascii=False), int(livemode)),
            )
            return dict(conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())

    @staticmethod
    def _expire_pending_checkouts(conn: sqlite3.Connection, account_id: str, now: int) -> None:
        """Close unusable local checkout records without deciding payment state.

        A late, verified paid webhook may still settle an expired local order.
        """
        conn.execute(
            """UPDATE orders SET status='expired'
               WHERE account_id=? AND provider='stripe' AND status='pending'
                 AND checkout_expires_at IS NOT NULL AND checkout_expires_at<=?""",
            (account_id, now),
        )
        # An interrupted process can leave a pending order with no redirect URL.
        conn.execute(
            """UPDATE orders SET status='failed'
               WHERE account_id=? AND provider='stripe' AND status='pending'
                 AND provider_order_id IS NULL AND checkout_url IS NULL
                 AND created_at<=?""",
            (account_id, now - 30 * 60),
        )

    def fail_stripe_checkout(self, order_id: str) -> None:
        """Mark a checkout that could not return a usable Stripe redirect."""
        with self._transaction() as conn:
            conn.execute(
                """UPDATE orders SET status='failed'
                   WHERE id=? AND provider='stripe' AND status='pending'
                     AND provider_order_id IS NULL""",
                (order_id,),
            )

    def attach_stripe_checkout(self, order_id: str, session_id: str,
                               checkout_url: str, expires_at: int) -> Dict:
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id=? AND provider='stripe'",
                               (order_id,)).fetchone()
            if not row:
                raise BillingError("订单不存在", 404)
            if row["status"] in {"paid", "refunded"}:
                raise BillingError("订单已处理，不能重新关联收银台", 409)
            if row["provider_order_id"] and row["provider_order_id"] != session_id:
                raise BillingError("订单已关联其他收银台", 409)
            expected_prefix = "cs_live_" if row["stripe_livemode"] else "cs_test_"
            if not session_id.startswith(expected_prefix):
                raise BillingError("Stripe 收银台环境与订单不一致", 409)
            conn.execute(
                """UPDATE orders SET status='pending',provider_order_id=?,checkout_url=?,
                   checkout_expires_at=? WHERE id=?""",
                (session_id, checkout_url, int(expires_at), order_id),
            )
            return dict(conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())

    @staticmethod
    def _public_order(row: sqlite3.Row) -> Dict:
        return {
            "order_id": row["id"], "product_id": row["product_id"],
            "provider": row["provider"], "status": row["status"],
            "amount_fen": int(row["amount_fen"]), "currency": row["currency"],
            "credits": int(row["credits"]), "created_at": int(row["created_at"]),
            "paid_at": row["paid_at"],
            "refunded_fen": int(row["refunded_fen"]),
            "live": bool(row["stripe_livemode"]) if row["provider"] == "stripe" else False,
        }

    def order(self, account_id: str, order_id: str) -> Optional[Dict]:
        with self._transaction() as conn:
            self._expire_pending_checkouts(conn, account_id, int(self._now()))
            row = conn.execute("SELECT * FROM orders WHERE account_id=? AND id=?",
                               (account_id, order_id)).fetchone()
            return self._public_order(row) if row else None

    def orders(self, account_id: str, limit: int = 30) -> List[Dict]:
        limit = max(1, min(int(limit), 100))
        with self._transaction() as conn:
            self._expire_pending_checkouts(conn, account_id, int(self._now()))
            rows = conn.execute(
                "SELECT * FROM orders WHERE account_id=? ORDER BY created_at DESC LIMIT ?",
                (account_id, limit),
            ).fetchall()
            return [self._public_order(row) for row in rows]

    def admin_orders(self, limit: int = 100) -> List[Dict]:
        """Read-only reconciliation view; caller must enforce administrator auth."""
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT o.*,p.primary_email AS account_email,
                          (SELECT COALESCE(SUM(amount_fen),0) FROM stripe_refunds r
                           WHERE r.payment_intent_id=o.payment_intent_id) AS provider_refunded_fen
                   FROM orders o LEFT JOIN auth_profiles p ON p.account_id=o.account_id
                   ORDER BY o.created_at DESC,o.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [
                {**self._public_order(row), "account_id": row["account_id"],
                 "account_email": row["account_email"],
                 "provider_refunded_fen": int(row["provider_refunded_fen"] or 0),
                 "reconciliation_required": int(row["provider_refunded_fen"] or 0)
                 != int(row["refunded_fen"])}
                for row in rows
            ]

    def apply_stripe_checkout_event(self, event_id: str, payload_hash: str,
                                    session: Dict) -> Dict:
        """Settle only a known, exact Checkout Session; event and grant are atomic."""
        if not isinstance(event_id, str) or not re.fullmatch(r"evt_[A-Za-z0-9]+", event_id):
            raise BillingError("Stripe 事件 ID 无效", 400)
        order_id = (session.get("metadata") or {}).get("order_id")
        if not isinstance(order_id, str):
            return {"status": "ignored"}
        now = int(self._now())
        with self._transaction() as conn:
            prior = conn.execute(
                "SELECT payload_hash FROM payment_events WHERE provider='stripe' AND event_id=?",
                (event_id,),
            ).fetchone()
            if prior:
                if prior["payload_hash"] != payload_hash:
                    raise BillingError("Stripe 事件 ID 与内容冲突", 409)
                return {"status": "duplicate"}
            order = conn.execute(
                "SELECT * FROM orders WHERE id=? AND provider='stripe'", (order_id,),
            ).fetchone()
            if not order:
                return {"status": "ignored"}
            metadata = session.get("metadata") or {}
            if (session.get("id") != order["provider_order_id"]
                    or session.get("client_reference_id") != order_id
                    or session.get("mode") != "payment"
                    or metadata.get("account_id") != order["account_id"]
                    or metadata.get("product_id") != order["product_id"]
                    or session.get("currency", "").upper() != order["currency"]
                    or session.get("amount_total") != order["amount_fen"]):
                raise BillingError("Stripe 订单信息不匹配", 409)
            if session.get("payment_status") != "paid":
                return {"status": "pending"}
            payment_intent_id = session.get("payment_intent")
            if order["stripe_livemode"] and (not isinstance(payment_intent_id, str)
                                             or not payment_intent_id.startswith("pi_")):
                raise BillingError("正式支付缺少 PaymentIntent，无法关联退款", 409)
            if payment_intent_id is not None and (not isinstance(payment_intent_id, str)
                                                  or not payment_intent_id.startswith("pi_")):
                raise BillingError("Stripe PaymentIntent 无效", 409)
            if order["payment_intent_id"] and order["payment_intent_id"] != payment_intent_id:
                raise BillingError("Stripe PaymentIntent 与订单不一致", 409)
            if order["status"] not in {"paid", "partially_refunded"}:
                if order["status"] == "refunded":
                    return {"status": "refunded", "order_id": order_id}
                product = json.loads(order["product_snapshot_json"] or "null")
                if not isinstance(product, dict):
                    raise BillingError("订单缺少商品快照", 409)
                balance_before = self._active_balance(conn, order["account_id"], now)
                reference = "order:" + order_id
                conn.execute(
                    """UPDATE orders SET status='paid',paid_at=?,payment_intent_id=? WHERE id=?""",
                    (now, payment_intent_id, order_id),
                )
                conn.execute(
                    """INSERT INTO credit_grants
                       (id,account_id,kind,product_id,granted,remaining,max_chars_per_job,
                        expires_at,reference,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("gr_" + uuid.uuid4().hex, order["account_id"], product["kind"],
                     order["product_id"], order["credits"], order["credits"],
                     product["max_chars_per_job"], now + product["valid_days"] * 86400,
                     reference, now),
                )
                conn.execute(
                    """INSERT INTO ledger_entries
                       (account_id,delta,kind,reference,balance_after,metadata_json,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (order["account_id"], order["credits"], "grant", reference,
                     balance_before + order["credits"],
                     json.dumps({"product_id": order["product_id"],
                                 "provider": "stripe"}, ensure_ascii=False), now),
                )
            elif payment_intent_id and not order["payment_intent_id"]:
                conn.execute("UPDATE orders SET payment_intent_id=? WHERE id=?",
                             (payment_intent_id, order_id))
            conn.execute(
                """INSERT INTO payment_events(provider,event_id,payload_hash,processed_at)
                   VALUES('stripe',?,?,?)""", (event_id, payload_hash, now),
            )
            if payment_intent_id:
                refund = self._refund_total(conn, payment_intent_id)
                if refund:
                    return self._reconcile_refund(conn, order_id, refund, now)
            return {"status": order["status"] if order["status"] == "partially_refunded"
                    else "paid", "order_id": order_id}

    @staticmethod
    def _refund_total(conn: sqlite3.Connection, payment_intent_id: str) -> Optional[Dict]:
        row = conn.execute(
            """SELECT SUM(amount_fen) AS amount_fen, MIN(currency) AS currency,
                      COUNT(DISTINCT currency) AS currencies
               FROM stripe_refunds WHERE payment_intent_id=?""",
            (payment_intent_id,),
        ).fetchone()
        if not row or row["amount_fen"] is None:
            return None
        if row["currencies"] != 1:
            raise BillingError("Stripe 退款币种不一致", 409)
        return {"payment_intent_id": payment_intent_id,
                "amount_fen": int(row["amount_fen"]), "currency": row["currency"]}

    @staticmethod
    def _recalculate_grant_remaining(conn: sqlite3.Connection, grant_id: str,
                                     now: int) -> None:
        """Keep released reservations below the post-refund entitlement ceiling."""
        conn.execute(
            """UPDATE credit_grants
               SET remaining=MAX(0,granted-refunded_credits-
                   (SELECT COALESCE(SUM(a.amount),0)
                    FROM usage_allocations a
                    JOIN usage_reservations r ON r.job_id=a.job_id
                    WHERE a.grant_id=credit_grants.id
                      AND r.status IN ('reserved','committed')))
               WHERE id=? AND revoked_at IS NULL
                 AND (expires_at IS NULL OR expires_at>?)""",
            (grant_id, now),
        )

    def _reconcile_refund(self, conn: sqlite3.Connection, order_id: str,
                          refund: Dict, now: int) -> Dict:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if (not order or order["status"] not in {"paid", "partially_refunded", "refunded"}
                or refund["amount_fen"] > order["amount_fen"]
                or refund["currency"] != order["currency"]):
            raise BillingError("Stripe 退款与订单金额或状态不匹配", 409)
        status = ("refunded" if refund["amount_fen"] == order["amount_fen"]
                  else "partially_refunded")
        if int(order["refunded_fen"]) == refund["amount_fen"]:
            return {"status": status, "order_id": order_id}
        if int(order["refunded_fen"]) > refund["amount_fen"]:
            raise BillingError("Stripe 累计退款金额不能倒退", 409)
        balance_before = self._active_balance(conn, order["account_id"], now)
        reference = "order:" + order_id
        grant = conn.execute(
            "SELECT * FROM credit_grants WHERE account_id=? AND reference=?",
            (order["account_id"], reference),
        ).fetchone()
        if not grant:
            raise BillingError("退款订单缺少额度发放记录", 409)
        target_credits = (int(order["credits"]) * refund["amount_fen"]
                          // int(order["amount_fen"]))
        if status == "refunded":
            target_credits = int(order["credits"])
            conn.execute(
                "UPDATE credit_grants SET refunded_credits=?,remaining=0,revoked_at=? WHERE id=?",
                (target_credits, now, grant["id"]),
            )
        else:
            conn.execute("UPDATE credit_grants SET refunded_credits=? WHERE id=?",
                         (target_credits, grant["id"]))
            self._recalculate_grant_remaining(conn, grant["id"], now)
        conn.execute("UPDATE orders SET status=?,refunded_fen=? WHERE id=?",
                     (status, refund["amount_fen"], order_id))
        conn.execute("UPDATE stripe_refunds SET applied_at=? WHERE payment_intent_id=?",
                     (now, refund["payment_intent_id"]))
        balance_after = self._active_balance(conn, order["account_id"], now)
        conn.execute(
            """INSERT INTO ledger_entries
               (account_id,delta,kind,reference,balance_after,metadata_json,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (order["account_id"], balance_after - balance_before,
             "refund" if status == "refunded" else "partial_refund",
             reference if status == "refunded" else f"{reference}:{refund['amount_fen']}",
             balance_after, json.dumps({"provider": "stripe", "product_id": order["product_id"],
                                        "refunded_fen": refund["amount_fen"],
                                        "refunded_credits": target_credits,
                                        "revoked_unused_credits": balance_before - balance_after},
                                       ensure_ascii=False), now),
        )
        return {"status": status, "order_id": order_id}

    def apply_stripe_succeeded_refund(self, event_id: str, payload_hash: str,
                                      refund_object: Dict) -> Dict:
        """Revoke unused credits when successful refunds cumulatively cover the order."""
        if not isinstance(event_id, str) or not re.fullmatch(r"evt_[A-Za-z0-9]+", event_id):
            raise BillingError("Stripe 事件 ID 无效", 400)
        refund_id = refund_object.get("id")
        payment_intent_id = refund_object.get("payment_intent")
        amount = refund_object.get("amount")
        refund_status = refund_object.get("status")
        currency = refund_object.get("currency")
        if (not isinstance(payment_intent_id, str) or not payment_intent_id.startswith("pi_")
                or not isinstance(refund_id, str) or not refund_id.startswith("re_")
                or not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0
                or not isinstance(currency, str)):
            raise BillingError("Stripe 退款事件字段无效", 400)
        if refund_status != "succeeded":
            return {"status": "refund_not_succeeded"}
        now = int(self._now())
        with self._transaction() as conn:
            prior = conn.execute(
                "SELECT payload_hash FROM payment_events WHERE provider='stripe' AND event_id=?",
                (event_id,),
            ).fetchone()
            if prior:
                if prior["payload_hash"] != payload_hash:
                    raise BillingError("Stripe 事件 ID 与内容冲突", 409)
                return {"status": "duplicate"}
            existing = conn.execute("SELECT * FROM stripe_refunds WHERE refund_id=?",
                                    (refund_id,)).fetchone()
            if existing and (existing["amount_fen"] != amount
                             or existing["currency"] != currency.upper()
                             or existing["payment_intent_id"] != payment_intent_id):
                raise BillingError("Stripe 退款与已有记录冲突", 409)
            conn.execute(
                """INSERT OR IGNORE INTO stripe_refunds
                   (refund_id,payment_intent_id,event_id,amount_fen,currency,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (refund_id, payment_intent_id, event_id, amount, currency.upper(), now),
            )
            conn.execute(
                """INSERT INTO payment_events(provider,event_id,payload_hash,processed_at)
                   VALUES('stripe',?,?,?)""", (event_id, payload_hash, now),
            )
            order = conn.execute(
                "SELECT id FROM orders WHERE provider='stripe' AND payment_intent_id=?",
                (payment_intent_id,),
            ).fetchone()
            if not order:
                return {"status": "pending_order"}
            refund = self._refund_total(conn, payment_intent_id)
            return self._reconcile_refund(conn, order["id"], refund, now)

    def reserve(self, account_id: str, job_id: str, text: str, strength: str,
                fingerprint: Optional[str] = None) -> Dict:
        if strength not in STRENGTH_MULTIPLIER_MILLI:
            raise BillingError("strength 参数无效", 400)
        chars = billable_chars(text)
        if chars <= 0:
            raise BillingError("没有可计费文字", 400)
        multiplier = STRENGTH_MULTIPLIER_MILLI[strength]
        required = (chars * multiplier + 999) // 1000
        fingerprint = fingerprint or request_fingerprint(text, strength)
        now = int(self._now())
        reused = False
        with self._transaction() as conn:
            self._ensure_account(conn, account_id, now)
            existing = conn.execute(
                "SELECT * FROM usage_reservations WHERE job_id=?", (job_id,),
            ).fetchone()
            if existing:
                same = (existing["account_id"] == account_id
                        and existing["request_hash"] == fingerprint
                        and existing["strength"] == strength
                        and int(existing["billable_chars"]) == chars)
                if not same:
                    raise BillingError("任务幂等键与原请求不一致", 409)
                return {
                    "job_id": job_id, "billable_chars": chars,
                    "reserved": int(existing["reserved"]),
                    "status": existing["status"],
                    "balance_after": self._active_balance(conn, account_id, now),
                    "reused": True,
                }

            grants = self._active_grants(conn, account_id, now)
            paid = [row for row in grants if row["kind"] != "welcome"]
            max_chars = max((int(row["max_chars_per_job"]) for row in grants), default=0)
            balance = sum(int(row["remaining"]) for row in grants)
            if strength != "conservative" and not paid:
                raise BillingError("免费体验仅支持保守模式；请购买字数包或月卡。", 402, {
                    "balance": balance, "max_chars_per_job": max_chars,
                    "upgrade_required": True,
                })
            if chars > max_chars:
                raise BillingError(
                    f"本次 {chars} 字，超过当前单次 {max_chars} 字上限。", 402,
                    {"billable_chars": chars, "max_chars_per_job": max_chars,
                     "upgrade_required": True},
                )
            if required > balance:
                raise BillingError(
                    f"需要 {required} 字额度，当前剩余 {balance} 字。", 402,
                    {"required": required, "balance": balance,
                     "upgrade_required": True},
                )

            conn.execute(
                """INSERT INTO usage_reservations
                   (job_id,account_id,request_hash,strength,billable_chars,
                    multiplier_milli,reserved,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (job_id, account_id, fingerprint, strength, chars, multiplier,
                 required, "reserved", now),
            )
            remaining = required
            for grant in grants:
                if remaining <= 0:
                    break
                take = min(remaining, int(grant["remaining"]))
                if take <= 0:
                    continue
                changed = conn.execute(
                    "UPDATE credit_grants SET remaining=remaining-? WHERE id=? AND remaining>=?",
                    (take, grant["id"], take),
                ).rowcount
                if changed != 1:
                    raise BillingError("额度并发预占失败，请重试", 409)
                conn.execute(
                    "INSERT INTO usage_allocations(job_id,grant_id,amount) VALUES(?,?,?)",
                    (job_id, grant["id"], take),
                )
                remaining -= take
            if remaining:
                raise BillingError("额度预占不完整，请重试", 409)
            balance_after = balance - required
            conn.execute(
                """INSERT INTO ledger_entries
                   (account_id,delta,kind,reference,balance_after,metadata_json,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (account_id, -required, "reserve", "job:" + job_id, balance_after,
                 json.dumps({"strength": strength, "billable_chars": chars,
                             "multiplier_milli": multiplier}, ensure_ascii=False), now),
            )
        return {
            "job_id": job_id, "billable_chars": chars, "reserved": required,
            "status": "reserved", "balance_after": balance_after,
            "reused": reused,
        }

    def finalize(self, job_id: str, success: bool, accepted: int = 0,
                 usage: Optional[Dict] = None) -> Dict:
        now = int(self._now())
        usage = usage or {}
        with self._transaction() as conn:
            reservation = conn.execute(
                "SELECT * FROM usage_reservations WHERE job_id=?", (job_id,),
            ).fetchone()
            if not reservation:
                raise BillingError("计费预占不存在", 404)
            account_id = reservation["account_id"]
            if reservation["status"] != "reserved":
                released = 0
                if reservation["status"] == "released":
                    entry = conn.execute(
                        """SELECT delta FROM ledger_entries
                           WHERE account_id=? AND kind='release' AND reference=?""",
                        (account_id, "job:" + job_id),
                    ).fetchone()
                    released = max(0, int(entry["delta"])) if entry else 0
                return {
                    "job_id": job_id, "status": reservation["status"],
                    "charged": int(reservation["reserved"])
                               if reservation["status"] == "committed" else 0,
                    "released": released,
                    "balance": self._active_balance(conn, account_id, now),
                    "reused": True,
                    "input_tokens": int(reservation["input_tokens"]),
                    "output_tokens": int(reservation["output_tokens"]),
                }

            try:
                input_tokens = max(0, int(usage.get("input_tokens") or 0))
            except (TypeError, ValueError, OverflowError):
                input_tokens = 0
            try:
                output_tokens = max(0, int(usage.get("output_tokens") or 0))
            except (TypeError, ValueError, OverflowError):
                output_tokens = 0
            try:
                llm_requests = max(0, int(usage.get("requests") or 0))
            except (TypeError, ValueError, OverflowError):
                llm_requests = 0
            try:
                total_tokens = max(0, int(usage.get("total_tokens") or 0))
            except (TypeError, ValueError, OverflowError):
                total_tokens = 0
            if not total_tokens:
                total_tokens = input_tokens + output_tokens
            reserved = int(reservation["reserved"])
            if success and int(accepted) > 0:
                status = "committed"
                charged, released = reserved, 0
                balance = self._active_balance(conn, account_id, now)
                conn.execute(
                    """UPDATE usage_reservations SET status=?,input_tokens=?,output_tokens=?,
                       finalized_at=? WHERE job_id=?""",
                    (status, input_tokens, output_tokens, now, job_id),
                )
                conn.execute(
                    """INSERT INTO ledger_entries
                       (account_id,delta,kind,reference,balance_after,metadata_json,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (account_id, 0, "settle", "job:" + job_id, balance,
                     json.dumps({"accepted": int(accepted), "input_tokens": input_tokens,
                                 "output_tokens": output_tokens,
                                 "total_tokens": total_tokens,
                                 "llm_requests": llm_requests}, ensure_ascii=False), now),
                )
            else:
                allocations = conn.execute(
                    "SELECT grant_id,amount FROM usage_allocations WHERE job_id=?",
                    (job_id,),
                ).fetchall()
                balance_before = self._active_balance(conn, account_id, now)
                status = "released"
                conn.execute(
                    """UPDATE usage_reservations SET status=?,input_tokens=?,output_tokens=?,
                       finalized_at=? WHERE job_id=?""",
                    (status, input_tokens, output_tokens, now, job_id),
                )
                for item in allocations:
                    self._recalculate_grant_remaining(conn, item["grant_id"], now)
                charged = 0
                balance = self._active_balance(conn, account_id, now)
                released = balance - balance_before
                conn.execute(
                    """INSERT INTO ledger_entries
                       (account_id,delta,kind,reference,balance_after,metadata_json,created_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (account_id, released, "release", "job:" + job_id, balance,
                     json.dumps({"reason": "failed_or_no_accepted_candidate",
                                 "reservation_released": reserved,
                                 "expired_or_revoked_credits": reserved - released,
                                 "input_tokens": input_tokens,
                                 "output_tokens": output_tokens,
                                 "total_tokens": total_tokens,
                                 "llm_requests": llm_requests}, ensure_ascii=False), now),
                )
        return {
            "job_id": job_id, "status": status, "charged": charged,
            "released": released, "balance": balance, "reused": False,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": total_tokens, "llm_requests": llm_requests,
        }

    def release_stale(self, max_age_seconds: int) -> int:
        cutoff = int(self._now()) - max(1, int(max_age_seconds))
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT job_id FROM usage_reservations WHERE status='reserved' AND created_at<?",
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
        released = 0
        for row in rows:
            result = self.finalize(row["job_id"], success=False, accepted=0)
            if result["status"] == "released" and not result["reused"]:
                released += 1
        return released

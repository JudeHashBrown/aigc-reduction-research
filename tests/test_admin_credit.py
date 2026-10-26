"""Admin credit grants stay auditable, idempotent, and credit-only."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

from auth import AuthStore  # noqa: E402
from billing import BillingError, BillingStore  # noqa: E402


def _account(auth: AuthStore, subject: str, email: str) -> str:
    session = auth.rotate_authenticated(
        auth.create_pre_auth()["token"], provider="google", subject=subject,
        email=email,
    )
    return session["account_id"]


def _expect_error(action, status: int):
    try:
        action()
    except BillingError as exc:
        assert exc.status == status, str(exc)
    else:
        raise AssertionError(f"Expected BillingError({status})")


def run():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "state.sqlite3"
        clock = [int(time.time())]
        billing = BillingStore(path, now=lambda: clock[0])
        auth = AuthStore(path, b"admin-credit-test-secret-at-least-32-bytes")
        actor = _account(auth, "admin-credit-actor", "admin@example.com")
        target = _account(auth, "admin-credit-target", "member@example.com")
        other = _account(auth, "admin-credit-other", "other@example.com")
        request_id = str(uuid.uuid4())
        args = (actor, target, "member@example.com", 1200, 30,
                "补偿一次服务中断", request_id)

        first = billing.grant_admin_credit(*args)
        assert first["reused"] is False
        assert first["balance_after"] == 2000
        assert first["expires_at"] == clock[0] + 30 * 86400
        summary = billing.summary(target)
        assert summary["balance"] == 2000
        assert summary["max_chars_per_job"] == 800
        assert summary["plan_id"] == "free"
        assert summary["allowed_strengths"] == ["conservative"]
        _expect_error(lambda: billing.reserve(target, "admin-credit-balanced", "甲乙", "balanced"), 402)
        _expect_error(lambda: billing.reserve(target, "admin-credit-too-long", "甲" * 801,
                                              "conservative"), 402)

        again = billing.grant_admin_credit(*args)
        assert again["reused"] is True
        assert billing.summary(target)["balance"] == 2000
        _expect_error(lambda: billing.grant_admin_credit(
            actor, target, "member@example.com", 1201, 30,
            "补偿一次服务中断", request_id), 409)
        _expect_error(lambda: billing.grant_admin_credit(
            actor, other, "other@example.com", 1200, 30,
            "补偿一次服务中断", request_id), 409)
        _expect_error(lambda: billing.grant_admin_credit(
            actor, target, "other@example.com", 1200, 30,
            "补偿一次服务中断", str(uuid.uuid4())), 409)
        _expect_error(lambda: billing.grant_admin_credit(
            actor, "acct_missing", "missing@example.com", 1200, 30,
            "补偿一次服务中断", str(uuid.uuid4())), 404)

        for invalid in (0, -1, 1_000_001, True, "100"):
            _expect_error(lambda value=invalid: billing.grant_admin_credit(
                actor, target, "member@example.com", value, 30,
                "补偿一次服务中断", str(uuid.uuid4())), 400)
        for invalid in (-1, 7, 366, "30"):
            _expect_error(lambda value=invalid: billing.grant_admin_credit(
                actor, target, "member@example.com", 100, value,
                "补偿一次服务中断", str(uuid.uuid4())), 400)
        _expect_error(lambda: billing.grant_admin_credit(
            actor, target, "member@example.com", 100, 30,
            "短", str(uuid.uuid4())), 400)
        _expect_error(lambda: billing.grant_admin_credit(
            actor, target, "member@example.com", 100, 30,
            "补偿一次服务中断", "not-a-uuid"), 400)

        with sqlite3.connect(path) as db:
            count = db.execute("SELECT COUNT(*) FROM admin_credit_grants WHERE request_id=?",
                               (request_id,)).fetchone()[0]
            grant_count = db.execute("SELECT COUNT(*) FROM credit_grants WHERE reference=?",
                                     ("admin:" + request_id,)).fetchone()[0]
            audit = db.execute("""SELECT actor_account_id,target_account_id,credits,reason
                               FROM admin_credit_grants WHERE request_id=?""",
                               (request_id,)).fetchone()
        assert count == grant_count == 1
        assert audit == (actor, target, 1200, "补偿一次服务中断")
        ledger = [row for row in billing.ledger(target) if row["reference"] == "admin:" + request_id]
        assert len(ledger) == 1 and ledger[0]["delta"] == 1200
        assert "补偿一次服务中断" not in str(ledger)

        # A repeated request after expiry does not mint a second grant.
        clock[0] += 30 * 86400 + 1
        assert billing.summary(target)["balance"] == 800
        assert billing.grant_admin_credit(*args)["reused"] is True
        assert billing.summary(target)["balance"] == 800

        # Zero days is the explicit non-expiring option.
        forever = billing.grant_admin_credit(
            actor, target, "member@example.com", 500, 0,
            "活动赠送额度", str(uuid.uuid4()))
        assert forever["expires_at"] is None
        assert billing.summary(target)["balance"] == 1300

        paid = _account(auth, "admin-credit-paid", "paid@example.com")
        billing.mock_checkout(paid, "pack_3k", "admin_credit_paid_setup")
        paid_before = billing.summary(paid)
        billing.grant_admin_credit(
            actor, paid, "paid@example.com", 1000, 365,
            "订单补发额度", str(uuid.uuid4()))
        paid_after = billing.summary(paid)
        assert paid_after["max_chars_per_job"] == paid_before["max_chars_per_job"]
        assert paid_after["allowed_strengths"] == paid_before["allowed_strengths"]
        assert paid_after["plan_id"] == paid_before["plan_id"]
        clock[0] += 91 * 86400
        paid_expired = billing.summary(paid)
        assert paid_expired["balance"] == 1800
        assert paid_expired["max_chars_per_job"] == 800
        assert paid_expired["allowed_strengths"] == ["conservative"]
        assert paid_expired["plan_id"] == "free"

        concurrent_id = str(uuid.uuid4())
        concurrent_args = (actor, other, "other@example.com", 200, 365,
                           "并发测试发放", concurrent_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: billing.grant_admin_credit(*concurrent_args), range(2)))
        assert sorted(row["reused"] for row in results) == [False, True]
        assert billing.summary(other)["balance"] == 1000


if __name__ == "__main__":
    run()
    print("✓ 管理员额度发放、审计、幂等与权益边界")

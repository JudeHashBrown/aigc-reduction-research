"""本地计费账本测试。

这里不测真实支付平台，只验证商业化 MVP 中最容易出错的
三件事：服务端套餐、原子额度预占和失败回滚。
"""
from __future__ import annotations

import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "engine"))

from billing import BillingError, BillingStore, PRODUCTS, billable_chars
import humanizer_bilingual as humanizer
from llm import MockClient


def expect_billing_error(fn, status):
    try:
        fn()
    except BillingError as exc:
        assert exc.status == status, f"期望 {status}，实际 {exc.status}: {exc}"
        return exc
    raise AssertionError(f"期望 BillingError({status})")


def make_store(now=None):
    folder = tempfile.TemporaryDirectory()
    store = BillingStore(Path(folder.name) / "billing.sqlite3", now=now)
    return folder, store


def test_billable_character_contract():
    assert billable_chars("中 文\nA\t😀") == 4
    assert billable_chars(" \r\n\t\u3000") == 0
    # 按 Unicode 码点计量，而不是 UTF-8 字节数。
    assert billable_chars("😀") == 1
    try:
        billable_chars(None)
    except TypeError:
        pass
    else:
        raise AssertionError("非字符串应被拒绝")


def test_welcome_grant_and_catalog():
    folder, store = make_store()
    try:
        summary = store.summary("student-a")
        assert summary["balance"] == 800
        assert summary["max_chars_per_job"] == 800
        assert summary["allowed_strengths"] == ["conservative"]
        assert summary["plan_id"] == "free"

        catalog = {item["id"]: item for item in store.public_catalog()}
        assert catalog["free"]["credits"] == 800
        assert catalog["pack_3k"]["price_fen"] == 990
        assert catalog["student_month"]["credits"] == 20_000
        assert catalog["pro_month"]["credits"] == 60_000

        # 反复读取不能重复发放欢迎额度。
        assert store.summary("student-a")["balance"] == 800
        assert len([x for x in store.ledger("student-a")
                    if x["reference"] == "welcome:v1"]) == 1
    finally:
        folder.cleanup()


def test_mock_checkout_is_server_priced_and_idempotent():
    folder, store = make_store()
    try:
        first = store.mock_checkout("student-a", "pack_3k", "checkout_key_001")
        assert first["provider"] == "mock"
        assert first["status"] == "paid"
        assert first["reused"] is False
        assert first["summary"]["balance"] == 3_800

        again = store.mock_checkout("student-a", "pack_3k", "checkout_key_001")
        assert again["order_id"] == first["order_id"]
        assert again["reused"] is True
        assert again["summary"]["balance"] == 3_800

        expect_billing_error(
            lambda: store.mock_checkout("student-a", "pack_10k", "checkout_key_001"),
            409,
        )
        expect_billing_error(
            lambda: store.mock_checkout("student-a", "not-a-real-product", "checkout_key_002"),
            400,
        )
        # 账本的支付金额、币种和额度只来自服务端产品表。
        assert PRODUCTS["pack_3k"]["price_fen"] == 990
        assert PRODUCTS["pack_3k"]["currency"] == "CNY"
    finally:
        folder.cleanup()


def test_strength_multiplier_entitlement_and_job_limit():
    folder, store = make_store()
    try:
        expect_billing_error(
            lambda: store.reserve("student-a", "job-balanced-free", "甲乙", "balanced"),
            402,
        )
        expect_billing_error(
            lambda: store.reserve("student-a", "job-too-long-free", "甲" * 801,
                                  "conservative"),
            402,
        )

        store.mock_checkout("student-a", "pack_3k", "checkout_key_003")
        deep = store.reserve("student-a", "job-deep", "甲乙丙", "deep")
        assert deep["billable_chars"] == 3
        assert deep["reserved"] == 5, "深度档 1.5 倍应向上取整"
        store.finalize("job-deep", success=False, accepted=0)

        expect_billing_error(
            lambda: store.reserve("student-a", "job-too-long-paid", "甲" * 3001,
                                  "conservative"),
            402,
        )
    finally:
        folder.cleanup()


def test_failure_zero_acceptance_and_success_settlement():
    folder, store = make_store()
    try:
        before = store.summary("student-a")["balance"]

        store.reserve("student-a", "job-failed", "甲" * 10, "conservative")
        assert store.summary("student-a")["balance"] == before - 10
        failed = store.finalize("job-failed", success=False, accepted=0,
                                usage={"input_tokens": 20, "output_tokens": 5})
        assert failed["status"] == "released"
        assert failed["released"] == 10
        assert store.summary("student-a")["balance"] == before

        store.reserve("student-a", "job-zero", "乙" * 11, "conservative")
        zero = store.finalize("job-zero", success=True, accepted=0)
        assert zero["status"] == "released"
        assert store.summary("student-a")["balance"] == before

        store.reserve("student-a", "job-ok", "丙" * 12, "conservative")
        settled = store.finalize("job-ok", success=True, accepted=1,
                                 usage={"input_tokens": 24, "output_tokens": 9})
        assert settled["status"] == "committed"
        assert settled["charged"] == 12
        assert store.summary("student-a")["balance"] == before - 12

        # 任务结算本身也必须幂等；重试不能再扣或再退。
        retried = store.finalize("job-ok", success=True, accepted=1)
        assert retried["reused"] is True
        assert retried["charged"] == 12
        assert store.summary("student-a")["balance"] == before - 12

        ledger_kinds = [x["kind"] for x in store.ledger("student-a", 20)]
        assert "reserve" in ledger_kinds
        assert "release" in ledger_kinds
        assert "settle" in ledger_kinds
    finally:
        folder.cleanup()


def test_deterministic_english_s11_rewrite_commits_reserved_quota():
    folder, store = make_store()
    try:
        source = (
            "It was found that the method may improve accuracy. "
            "The tool is fast, stable, and simple."
        )
        expected = (
            "The method may improve accuracy. "
            "The tool is fast, stable, and simple."
        )
        before = store.summary("student-a")["balance"]
        reserved = store.reserve(
            "student-a", "job-en-s11-s01", source, "conservative")

        client = MockClient(lambda _text: "unsafe model output")
        result = humanizer.humanize(source, client, n_candidates=1)
        assert result["text"] == expected
        assert result["n_accepted"] == 1
        assert client.calls == []
        assert client.usage_summary()["requests"] == 0

        settled = store.finalize(
            "job-en-s11-s01", success=True,
            accepted=result["n_accepted"], usage=client.usage_summary())
        assert settled["status"] == "committed"
        assert settled["charged"] == reserved["reserved"]
        assert settled["llm_requests"] == 0
        assert store.summary("student-a")["balance"] == before - reserved["reserved"]
    finally:
        folder.cleanup()


def test_concurrent_reservations_cannot_overspend():
    folder, store = make_store()
    try:
        store.mock_checkout("student-a", "pack_3k", "checkout_key_004")
        assert store.summary("student-a")["balance"] == 3_800
        barrier = threading.Barrier(2)

        def reserve(job_id):
            barrier.wait(timeout=5)
            try:
                result = store.reserve("student-a", job_id, "甲" * 2500,
                                       "conservative")
                return "ok", result
            except BillingError as exc:
                return "error", exc.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, ["job-race-a", "job-race-b"]))

        assert sorted(kind for kind, _ in results) == ["error", "ok"]
        assert [value for kind, value in results if kind == "error"] == [402]
        assert store.summary("student-a")["balance"] == 1_300
    finally:
        folder.cleanup()


def test_expiry_and_stale_reservation_release():
    clock = [1_700_000_000]
    folder, store = make_store(now=lambda: clock[0])
    try:
        store.mock_checkout("student-a", "pack_3k", "checkout_key_005")
        store.reserve("student-a", "job-stale", "甲" * 100, "conservative")
        assert store.summary("student-a")["balance"] == 3_700

        clock[0] += 2 * 60 * 60 + 1
        assert store.release_stale(2 * 60 * 60) == 1
        assert store.summary("student-a")["balance"] == 3_800
        assert store.release_stale(2 * 60 * 60) == 0

        clock[0] += 90 * 24 * 60 * 60
        expired = store.summary("student-a")
        assert expired["balance"] == 800
        assert expired["plan_id"] == "free"
        assert expired["allowed_strengths"] == ["conservative"]
    finally:
        folder.cleanup()


def test_expired_grant_release_has_no_phantom_credits():
    clock = [1_700_000_000]
    folder, store = make_store(now=lambda: clock[0])
    try:
        store.mock_checkout("student-a", "pack_3k", "checkout_expiry_release")
        store.reserve("student-a", "job-expiry-release", "甲" * 100, "conservative")
        clock[0] += 90 * 24 * 60 * 60 + 1
        result = store.finalize("job-expiry-release", success=False)
        assert result["status"] == "released"
        assert result["released"] == 0
        assert result["balance"] == 800
        assert store.finalize("job-expiry-release", success=False)["released"] == 0
        release = next(entry for entry in store.ledger("student-a")
                       if entry["reference"] == "job:job-expiry-release"
                       and entry["kind"] == "release")
        assert release["delta"] == 0
        assert release["metadata"]["expired_or_revoked_credits"] == 100
    finally:
        folder.cleanup()


TESTS = [
    test_billable_character_contract,
    test_welcome_grant_and_catalog,
    test_mock_checkout_is_server_priced_and_idempotent,
    test_strength_multiplier_entitlement_and_job_limit,
    test_failure_zero_acceptance_and_success_settlement,
    test_deterministic_english_s11_rewrite_commits_reserved_quota,
    test_concurrent_reservations_cannot_overspend,
    test_expiry_and_stale_reservation_release,
    test_expired_grant_release_has_no_phantom_credits,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"✓ 计费账本 {len(TESTS)} 组：幂等、权益、并发预占、结算与过期全部正确")

"""本地计费账本测试。

这里不测真实支付平台，只验证商业化 MVP 中最容易出错的
三件事：服务端套餐、原子额度预占和失败回滚。
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "engine"))

from billing import (BillingError, BillingStore, PRODUCTS, billable_chars,
                     request_fingerprint)
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


def test_billable_unit_contract():
    assert billable_chars("中 文\nA\t😀") == 4
    assert billable_chars(" \r\n\t\u3000") == 0
    assert billable_chars("one two, 3") == 3
    assert billable_chars("cafe\u0301") == billable_chars("café") == 1
    assert billable_chars("ªª ºº ᵃᵃ") == 3
    assert billable_chars("\ua7cb\ua7cb") == 1  # Node 较新的 Latin 字母；后端不可计 2。
    assert billable_chars("\U00010d40\U00010d41") == 1  # 新 Unicode 十进制数字。
    assert billable_chars("a\u0897b") == 1  # 新 Unicode 组合附加符。
    assert billable_chars("a\u1b4eb") == 2  # 新 Unicode 标点不计、但切词。
    assert billable_chars("a\u061db") == 2  # 兼容服务器较旧的 Unicode 数据库。
    assert billable_chars("\U00011f50\U00011f51") == 1
    assert billable_chars("A\u200bB\ufe0f\x00") == 1
    assert billable_chars("A\u0890B") == 1  # 新 Unicode 格式字符不拆词。
    assert billable_chars("A\U00013439B") == 1
    assert billable_chars("don't don’t state-of-the-art 3.14") == 8
    assert billable_chars("汉字AI research") == 4
    assert billable_chars("カナ 한글") == 4
    assert billable_chars("カ\u3099") == 2  # 非拉丁组合附加符保持逐码点计。
    assert billable_chars("!，。—…") == 0
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
        assert summary["metering_version"] == 2
        assert summary["max_chars_per_job"] == 800
        assert summary["allowed_strengths"] == ["conservative"]
        assert summary["plan_id"] == "free"

        catalog = {item["id"]: item for item in store.public_catalog()}
        assert catalog["free"]["credits"] == 800
        assert all(item["metering_version"] == 2 for item in catalog.values())
        assert "1 个英文单词" in catalog["free"]["description"]
        assert catalog["pack_3k"]["price_fen"] == 990
        assert catalog["pack_3k"]["currency"] == "CNY"
        assert catalog["pack_3k"]["prices"] == {
            "CNY": {"currency": "CNY", "amount_minor": 990},
            "USD": {"currency": "USD", "amount_minor": 190},
        }
        expected_usd_prices = {
            "pack_3k": 190, "pack_10k": 590, "pack_30k": 1290,
            "student_month": 790, "pro_month": 1490,
        }
        for product_id, expected_cents in expected_usd_prices.items():
            quote = catalog[product_id]["prices"]["USD"]
            assert quote == {"currency": "USD", "amount_minor": expected_cents}
            assert expected_cents % 100 == 90
        assert catalog["student_month"]["credits"] == 20_000
        assert catalog["pro_month"]["credits"] == 60_000

        # 反复读取不能重复发放欢迎额度。
        assert store.summary("student-a")["balance"] == 800
        assert len([x for x in store.ledger("student-a")
                    if x["reference"] == "welcome:v1"]) == 1
        assert next(x for x in store.ledger("student-a")
                    if x["reference"] == "welcome:v1")["metadata"]["metering_version"] == 2
    finally:
        folder.cleanup()


def test_mock_checkout_is_server_priced_and_idempotent():
    folder, store = make_store()
    try:
        first = store.mock_checkout("student-a", "pack_3k", "checkout_key_001")
        assert first["provider"] == "mock"
        assert first["status"] == "paid"
        assert first["reused"] is False
        assert first["currency"] == "CNY"
        assert first["amount_minor"] == 990
        assert first["summary"]["balance"] == 3_800
        assert store.order("student-a", first["order_id"])["metering_version"] == 2

        again = store.mock_checkout("student-a", "pack_3k", "checkout_key_001")
        assert again["order_id"] == first["order_id"]
        assert again["reused"] is True
        assert again["summary"]["balance"] == 3_800

        expect_billing_error(
            lambda: store.mock_checkout("student-a", "pack_10k", "checkout_key_001"),
            409,
        )
        expect_billing_error(
            lambda: store.mock_checkout("student-a", "pack_3k", "checkout_key_001",
                                        currency="USD"),
            409,
        )
        expect_billing_error(
            lambda: store.mock_checkout("student-a", "not-a-real-product", "checkout_key_002"),
            400,
        )
        # 账本的支付金额、币种和额度只来自服务端产品表。
        assert PRODUCTS["pack_3k"]["price_fen"] == 990
        assert PRODUCTS["pack_3k"]["currency"] == "CNY"
        stripe_order = store.prepare_stripe_checkout(
            "student-a", "pack_3k", "checkout_stripe_v2")
        assert json.loads(stripe_order["product_snapshot_json"])["metering_version"] == 2
        assert store.order("student-a", stripe_order["id"])["metering_version"] == 2
        with store._transaction() as conn:
            conn.execute("UPDATE orders SET product_snapshot_json=? WHERE id=?",
                         (json.dumps(dict(PRODUCTS["pack_3k"])), stripe_order["id"]))
        assert store.order("student-a", stripe_order["id"])["metering_version"] == 1
    finally:
        folder.cleanup()


def test_usd_catalog_price_order_snapshot_and_currency_validation():
    folder, store = make_store()
    try:
        for bad in ("EUR", "usd", "", None, [], 1):
            expect_billing_error(
                lambda bad=bad: store.mock_checkout("buyer", "student_month",
                                                    "unsupported_currency", currency=bad),
                400,
            )
        paid = store.mock_checkout("buyer", "student_month", "usd_mock_order", currency="USD")
        assert paid["amount_minor"] == 790 and paid["currency"] == "USD"
        public_order = store.order("buyer", paid["order_id"])
        assert public_order["amount_fen"] == public_order["amount_minor"] == 790
        assert public_order["currency"] == "USD" and public_order["credits"] == 20_000
        with store._connect() as conn:
            snapshot = json.loads(conn.execute(
                "SELECT product_snapshot_json FROM orders WHERE id=?",
                (paid["order_id"],)).fetchone()[0])
        assert snapshot["currency"] == "USD"
        assert snapshot["price_minor"] == 790
        assert snapshot["name"] == "Student 30-day pass"
        assert store.mock_checkout("buyer", "student_month", "usd_mock_order",
                                   currency="USD")["reused"]
        expect_billing_error(lambda: store.mock_checkout(
            "buyer", "student_month", "usd_mock_order"), 409)
        stripe = store.prepare_stripe_checkout("buyer", "student_month", "usd_stripe_order",
                                               currency="USD")
        assert stripe["amount_fen"] == 790 and stripe["currency"] == "USD"
        assert store.prepare_stripe_checkout("buyer", "student_month", "usd_stripe_order",
                                             currency="USD")["id"] == stripe["id"]
        expect_billing_error(lambda: store.prepare_stripe_checkout(
            "buyer", "student_month", "usd_stripe_order"), 409)
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


def test_english_welcome_limit_matches_word_count():
    folder, store = make_store()
    try:
        within_limit = "word " * 800
        assert billable_chars(within_limit) == 800
        reservation = store.reserve("english-student", "job-english-800",
                                    within_limit, "conservative")
        assert reservation["billable_chars"] == reservation["reserved"] == 800
        assert reservation["metering_version"] == 2
        assert next(row for row in store.ledger("english-student")
                    if row["kind"] == "reserve")["metadata"]["metering_version"] == 2
        store.finalize("job-english-800", success=False)
        assert store.summary("english-student")["balance"] == 800

        over_limit = within_limit + "more"
        error = expect_billing_error(
            lambda: store.reserve("english-student", "job-english-801",
                                  over_limit, "conservative"), 402)
        assert error.details["billable_chars"] == 801
        assert expect_billing_error(
            lambda: store.reserve("english-student", "job-only-punctuation",
                                  "!? ；，", "conservative"), 400)
    finally:
        folder.cleanup()


def test_word_metering_rejects_costly_unmetered_text():
    folder, store = make_store()
    try:
        for job_id, text in (("job-long-word", "a" * 120_000),
                             ("job-punctuation", "a" + "!" * 119_999)):
            assert billable_chars(text) == 1
            error = expect_billing_error(
                lambda: store.reserve("density-student", job_id, text,
                                      "conservative"), 422)
            assert error.details["code"] == "text_density_limit"
            assert error.details["text_chars"] == 120_000
            assert error.details["max_text_chars"] == 256
            assert error.details["billable_units"] == 1
            assert error.details["metering_version"] == 2
            assert "No credits were charged" in error.details["error_en"]
        assert store.summary("density-student")["balance"] == 800
        assert not any(row["kind"] == "reserve"
                       for row in store.ledger("density-student"))

        # Normal English and Han/English prose stay well inside the safety
        # bound; the exact 256-codepoint floor remains predictable.
        samples = (("job-normal-english", "This paragraph uses evidence, citations, and measured claims."),
                   ("job-normal-mixed", "研究 uses evidence, and keeps facts."),
                   ("job-density-boundary", "word" + " " * 252))
        for job_id, text in samples:
            reserved = store.reserve("density-student", job_id, text,
                                     "conservative")
            assert reserved["reserved"] == billable_chars(text)
            assert reserved["metering_version"] == 2
            store.finalize(job_id, success=False)
        assert store.summary("density-student")["balance"] == 800
        assert expect_billing_error(
            lambda: store.reserve("density-student", "job-over-density-boundary",
                                  "word" + " " * 253, "conservative"), 422)
    finally:
        folder.cleanup()


def test_legacy_reservations_keep_character_metering_and_idempotence():
    folder, store = make_store(now=lambda: 1_700_000_000)
    try:
        assert store.summary("legacy-student")["balance"] == 800
        # Recreate a v1 database that predates the metering_version column.
        with store._connect() as conn:
            conn.execute("ALTER TABLE usage_reservations DROP COLUMN metering_version")
        store = BillingStore(store.path, now=lambda: 1_700_000_000)
        with store._connect() as conn:
            assert "metering_version" in {
                row["name"] for row in conn.execute("PRAGMA table_info(usage_reservations)")}

        def seed_v1(job_id, text):
            old_chars = sum(not char.isspace() for char in text)
            with store._transaction() as conn:
                grant = conn.execute("SELECT id FROM credit_grants WHERE account_id=?",
                                     ("legacy-student",)).fetchone()
                conn.execute("UPDATE credit_grants SET remaining=remaining-? WHERE id=?",
                             (old_chars, grant["id"]))
                conn.execute("""INSERT INTO usage_reservations
                    (job_id,account_id,request_hash,strength,billable_chars,
                     multiplier_milli,reserved,status,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (job_id, "legacy-student", request_fingerprint(text, "conservative"),
                     "conservative", old_chars, 1000, old_chars,
                     "reserved", 1_700_000_000))
                conn.execute("INSERT INTO usage_allocations(job_id,grant_id,amount) VALUES(?,?,?)",
                             (job_id, grant["id"], old_chars))
            return old_chars

        committed_old_chars = seed_v1("legacy-committed", "one two")
        assert committed_old_chars == 6 and billable_chars("one two") == 2
        reused = store.reserve("legacy-student", "legacy-committed", "one two",
                               "conservative")
        assert reused["reused"] and reused["metering_version"] == 1
        assert reused["billable_chars"] == reused["reserved"] == 6
        settled = store.finalize("legacy-committed", success=True, accepted=1)
        assert settled["charged"] == 6 and settled["metering_version"] == 1

        assert seed_v1("legacy-punctuation", "!!!") == 3
        assert store.reserve("legacy-student", "legacy-punctuation", "!!!",
                             "conservative")["metering_version"] == 1
        assert store.finalize("legacy-punctuation", success=False)["released"] == 3

        released_old_chars = seed_v1("legacy-released", "red blue")
        assert released_old_chars == 7
        released = store.finalize("legacy-released", success=False)
        assert released["status"] == "released" and released["metering_version"] == 1
        assert released["released"] == 7
        legacy_long_word = "a" * 300
        assert seed_v1("legacy-long-word", legacy_long_word) == 300
        assert store.reserve("legacy-student", "legacy-long-word", legacy_long_word,
                             "conservative")["metering_version"] == 1
        assert store.finalize("legacy-long-word", success=False)["released"] == 300
        assert store.summary("legacy-student")["balance"] == 794
        assert next(row for row in store.ledger("legacy-student")
                    if row["kind"] == "settle")["metadata"]["metering_version"] == 1
    finally:
        folder.cleanup()


def test_english_format_only_rewrite_releases_quota():
    folder, store = make_store()
    try:
        source = "**The method is clear.**"
        reserved = store.reserve("format-student", "job-format-only", source,
                                 "conservative")
        client = MockClient(lambda _text: "The method is clear.")
        result = humanizer.humanize(source, client, n_candidates=1,
                                    auto_english=True)
        assert result["text"] == source
        assert result["n_accepted"] == 0 and client.calls == []
        settled = store.finalize("job-format-only", success=True,
                                 accepted=result["n_accepted"],
                                 usage=client.usage_summary())
        assert settled["status"] == "released"
        assert settled["released"] == reserved["reserved"]
        assert store.summary("format-student")["balance"] == 800
    finally:
        folder.cleanup()


def test_user_requested_zero_safe_candidate_refunds_and_reports_unchanged():
    folder, store = make_store()
    try:
        source = "本研究对 126 份样本进行分析，见[1]。"
        before = store.summary("student-a")["balance"]
        reserved = store.reserve("student-a", "job-requested-reject", source,
                                 "conservative")
        client = MockClient(lambda _text: "本研究对 200 份样本进行分析，见[1]。")
        result = humanizer.humanize(source, client, n_candidates=1,
                                    user_requested=True)
        assert result["text"] == source and not result["changed"]
        assert result["n_accepted"] == result["n_safe_changes"] == 0
        assert result["no_change_reason"]
        settled = store.finalize("job-requested-reject", success=True,
                                 accepted=result["n_accepted"],
                                 usage=client.usage_summary())
        assert settled["status"] == "released"
        assert settled["released"] == reserved["reserved"]
        assert store.summary("student-a")["balance"] == before
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


def test_long_pass_and_queued_reservation_survive_restart():
    clock = [1_700_000_000]
    folder, store = make_store(now=lambda: clock[0])
    try:
        store.mock_checkout("student-a", "pro_month", "checkout_long_paper")
        assert store.summary("student-a")["max_chars_per_job"] == 60_000
        store.reserve("student-a", "job-long-paper", "甲" * 41_021, "conservative")
        from workspace_store import WorkspaceStore
        jobs = WorkspaceStore(store.path)
        jobs.claim_job("student-a", "request-long", "hash-long", "job-long-paper", 2,
                       request={"text": "甲" * 41_021, "strength": "conservative"})
        jobs.update_job("job-long-paper", billing={"status": "reserved"})
        clock[0] += 2 * 60 * 60 + 1
        assert BillingStore(store.path, now=lambda: clock[0]).release_stale(2 * 60 * 60) == 0
        assert jobs.get_job("student-a", "job-long-paper")["state"] == "queued"
    finally:
        folder.cleanup()


TESTS = [
    test_billable_unit_contract,
    test_welcome_grant_and_catalog,
    test_mock_checkout_is_server_priced_and_idempotent,
    test_usd_catalog_price_order_snapshot_and_currency_validation,
    test_strength_multiplier_entitlement_and_job_limit,
    test_english_welcome_limit_matches_word_count,
    test_word_metering_rejects_costly_unmetered_text,
    test_legacy_reservations_keep_character_metering_and_idempotence,
    test_english_format_only_rewrite_releases_quota,
    test_failure_zero_acceptance_and_success_settlement,
    test_deterministic_english_s11_rewrite_commits_reserved_quota,
    test_concurrent_reservations_cannot_overspend,
    test_expiry_and_stale_reservation_release,
    test_expired_grant_release_has_no_phantom_credits,
    test_long_pass_and_queued_reservation_survive_restart,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"✓ 计费账本 {len(TESTS)} 组：幂等、权益、并发预占、结算与过期全部正确")

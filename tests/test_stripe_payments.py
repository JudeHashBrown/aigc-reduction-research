"""Offline Stripe test/live contract tests; no real key or network is used."""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

from billing import BillingError, BillingStore, PRODUCTS  # noqa: E402
from payments import StripePaymentProvider  # noqa: E402


def expect_error(callback, status):
    try:
        callback()
    except BillingError as exc:
        assert exc.status == status, (exc.status, str(exc))
        return
    raise AssertionError(f"Expected BillingError {status}")


def test_stripe_order_and_webhook_idempotency():
    with tempfile.TemporaryDirectory() as folder:
        now = [int(time.time())]
        store = BillingStore(Path(folder) / "billing.sqlite3", now=lambda: now[0])
        assert store.summary("buyer")['balance'] == 800
        order = store.prepare_stripe_checkout("buyer", "student_month", "checkout_test_001")
        assert order["amount_fen"] == PRODUCTS["student_month"]["price_fen"]
        assert order["status"] == "pending"
        assert store.summary("buyer")["balance"] == 800
        assert store.prepare_stripe_checkout("buyer", "student_month", "checkout_test_001")["id"] == order["id"]
        expect_error(lambda: store.prepare_stripe_checkout(
            "buyer", "pack_3k", "checkout_test_001"), 409)
        store.attach_stripe_checkout(order["id"], "cs_test_123", "https://checkout.stripe.com/c/pay/123", now[0] + 3600)
        session = {
            "id": "cs_test_123", "client_reference_id": order["id"],
            "metadata": {"order_id": order["id"], "account_id": "buyer",
                         "product_id": "student_month"},
            "mode": "payment", "currency": "cny", "amount_total": 3990,
            "payment_status": "unpaid",
        }
        assert store.apply_stripe_checkout_event("evt_unpaid123", "hash1", session)["status"] == "pending"
        assert store.summary("buyer")["balance"] == 800
        paid_session = {**session, "payment_status": "paid"}
        forged = {**paid_session, "amount_total": 1}
        expect_error(lambda: store.apply_stripe_checkout_event("evt_forged123", "hash2", forged), 409)
        assert store.summary("buyer")["balance"] == 800
        paid = store.apply_stripe_checkout_event("evt_paid123", "hash3", paid_session)
        assert paid == {"status": "paid", "order_id": order["id"]}
        assert store.summary("buyer")["balance"] == 20_800
        assert store.apply_stripe_checkout_event("evt_paid123", "hash3", paid_session)["status"] == "duplicate"
        assert store.apply_stripe_checkout_event("evt_paid456", "hash4", paid_session)["status"] == "paid"
        assert store.summary("buyer")["balance"] == 20_800
        assert store.order("someone-else", order["id"]) is None
        assert len(store.orders("buyer")) == 1
        expect_error(lambda: store.apply_stripe_checkout_event("evt_paid123", "different", paid_session), 409)
        grants = [grant for grant in store.summary("buyer")["grants"]
                  if grant["product_id"] == "student_month"]
        assert len(grants) == 1
        assert grants[0]["expires_at"] == now[0] + 30 * 86400


def test_live_reconciliation_repairs_missed_webhooks_without_double_grants():
    with tempfile.TemporaryDirectory() as folder:
        store = BillingStore(Path(folder) / "billing.sqlite3")
        order = store.prepare_stripe_checkout("buyer", "pack_3k", "checkout_reconcile", livemode=True)
        store.attach_stripe_checkout(order["id"], "cs_live_reconcile",
                                     "https://checkout.stripe.com/c/pay/reconcile", int(time.time()) + 3600)
        session = {"id": "cs_live_reconcile", "object": "checkout.session", "livemode": True,
                   "client_reference_id": order["id"],
                   "metadata": {"order_id": order["id"], "account_id": "buyer", "product_id": "pack_3k"},
                   "mode": "payment", "currency": "cny", "amount_total": 990,
                   "payment_status": "paid", "payment_intent": "pi_reconcile"}
        refund = {"id": "re_reconcile", "object": "refund", "payment_intent": "pi_reconcile",
                  "amount": 990, "currency": "cny", "status": "succeeded"}
        observed = {"refunds": [refund]}
        fake = SimpleNamespace(StripeClient=lambda _key: SimpleNamespace(v1=SimpleNamespace(
            checkout=SimpleNamespace(sessions=SimpleNamespace(retrieve=lambda _id: session)),
            refunds=SimpleNamespace(retrieve=lambda _id: refund,
                                    list=lambda **_kw: {"data": observed["refunds"], "has_more": False}),
            disputes=SimpleNamespace(list=lambda **_kw: (_ for _ in ()).throw(
                AssertionError("payment reconciliation must not depend on dispute-read permission"))))))
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_live_fake",
                                  "STRIPE_WEBHOOK_SECRET": "whsec_fake", "STRIPE_LIVE_ENABLED": "1",
                                  "PUBLIC_ORIGIN": "https://rightthesis.com"}):
            provider = StripePaymentProvider(store)
            provider.stripe = fake
            provider.configured = True
            expect_error(lambda: provider.reconcile_order("another", order["id"]), 404)
            provider.reconcile_order("buyer", order["id"], audit_refunds=True)
            assert store.order("buyer", order["id"])["status"] == "refunded"
            assert store.summary("buyer")["balance"] == 800
            provider.reconcile_order("buyer", order["id"], audit_refunds=True)
            assert len([entry for entry in store.ledger("buyer")
                        if entry["kind"] == "grant" and entry["reference"] == "order:" + order["id"]]) == 1
            assert len([entry for entry in store.ledger("buyer") if entry["kind"] == "refund"]) == 1


def test_provider_modes_and_checkout_options():
    with tempfile.TemporaryDirectory() as folder:
        store = BillingStore(Path(folder) / "billing.sqlite3")
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_live_forbidden",
                                  "STRIPE_WEBHOOK_SECRET": "whsec_fake",
                                  "STRIPE_LIVE_ENABLED": "0"}):
            provider = StripePaymentProvider(store)
            assert not provider.configured
        captured = {}

        def create(*, params, options):
            captured["params"] = params
            captured["options"] = options
            return {"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay/123",
                    "expires_at": int(time.time()) + 3600}

        fake = SimpleNamespace(
            StripeClient=lambda _key: SimpleNamespace(v1=SimpleNamespace(
                checkout=SimpleNamespace(sessions=SimpleNamespace(create=create)))),
            Webhook=SimpleNamespace(construct_event=lambda raw, sig, secret: json.loads(raw)),
            error=SimpleNamespace(SignatureVerificationError=ValueError),
        )
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_not_real",
                                  "STRIPE_WEBHOOK_SECRET": "whsec_not_real",
                                  "STRIPE_LIVE_ENABLED": "0"}):
            provider = StripePaymentProvider(store)
            provider.stripe = fake
            provider.configured = True
            expect_error(lambda: provider.checkout("buyer", "pack_3k", "no_email_001",
                                                   origin="http://127.0.0.1:8877"), 403)
            assert store.orders("buyer") == []
            result = provider.checkout("buyer", "pack_3k", "checkout_test_002",
                                       origin="http://127.0.0.1:8877",
                                       customer_email="buyer@example.com")
            assert result["status"] == "pending"
            assert result["live"] is False
            assert captured["params"]["mode"] == "payment"
            assert captured["params"]["customer_email"] == "buyer@example.com"
            assert "allowed_payment_method_types" not in captured["params"]
            assert "payment_method_types" not in captured["params"]
            assert captured["params"]["line_items"][0]["price_data"]["unit_amount"] == 990
            assert "#/checkout/pro?order=" in captured["params"]["success_url"]
            assert captured["options"]["idempotency_key"].startswith("rightthesis-ord_")
            assert provider.checkout("buyer", "pack_3k", "checkout_test_002",
                                     origin="http://127.0.0.1:8877",
                                     customer_email="buyer@example.com")["reused"]
            expect_error(lambda: provider.checkout("buyer", "pack_3k", "checkout_test_003",
                                                    origin="http://evil.example",
                                                    customer_email="buyer@example.com"), 400)
            event = {"id": "evt_fake123", "livemode": False,
                     "type": "checkout.session.completed", "data": {"object": {
                         "id": "cs_test_123", "client_reference_id": result["order_id"],
                         "metadata": {"order_id": result["order_id"], "account_id": "buyer",
                                      "product_id": "pack_3k"},
                         "mode": "payment", "currency": "cny", "amount_total": 990,
                         "payment_status": "paid", "payment_intent": "pi_test_123"}}}
            raw = json.dumps(event).encode()
            assert provider.webhook(raw, "fake-signature")["status"] == "paid"
            assert store.summary("buyer")["balance"] == 3800


def test_live_mode_requires_opt_in_https_and_matching_webhook():
    with tempfile.TemporaryDirectory() as folder:
        store = BillingStore(Path(folder) / "billing.sqlite3")
        captured = {}

        def create(*, params, options):
            captured["params"] = params
            return {"id": "cs_live_123", "url": "https://checkout.stripe.com/c/pay/live",
                    "expires_at": int(time.time()) + 3600}

        fake = SimpleNamespace(
            StripeClient=lambda _key: SimpleNamespace(v1=SimpleNamespace(
                checkout=SimpleNamespace(sessions=SimpleNamespace(
                    create=create,
                    retrieve=lambda _id: captured["retrieved_session"])),
                refunds=SimpleNamespace(retrieve=lambda _id: captured["retrieved_refund"]),
                events=SimpleNamespace(retrieve=lambda _id: captured["retrieved_event"]))),
            Webhook=SimpleNamespace(construct_event=lambda raw, sig, secret: json.loads(raw)),
            error=SimpleNamespace(SignatureVerificationError=ValueError),
        )
        with patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_live_not_real", "STRIPE_WEBHOOK_SECRET": "whsec_not_real",
            "STRIPE_LIVE_ENABLED": "1", "PUBLIC_ORIGIN": "https://rightthesis.com",
        }):
            provider = StripePaymentProvider(store)
            provider.stripe = fake
            provider.configured = True
            assert provider.live
            assert provider.public_status()["checkout_enabled"]
            expect_error(lambda: provider.checkout("buyer", "pack_3k", "checkout_live_bad",
                                                   origin="https://evil.example",
                                                   customer_email="buyer@example.com"), 400)
            result = provider.checkout("buyer", "pack_3k", "checkout_live_001",
                                       origin="https://rightthesis.com",
                                       customer_email="buyer@example.com")
            assert result["live"] is True
            assert captured["params"]["customer_email"] == "buyer@example.com"
            assert "allowed_payment_method_types" not in captured["params"]
            assert "payment_method_types" not in captured["params"]
            assert store.order("buyer", result["order_id"])["live"] is True
            event = {"id": "evt_live123", "livemode": True,
                     "type": "checkout.session.completed", "data": {"object": {
                         "id": "cs_live_123", "client_reference_id": result["order_id"],
                         "metadata": {"order_id": result["order_id"], "account_id": "buyer",
                                      "product_id": "pack_3k"},
                         "mode": "payment", "currency": "cny", "amount_total": 990,
                         "payment_status": "paid", "payment_intent": "pi_live_123"}}}
            expect_error(lambda: provider.webhook(json.dumps({**event, "livemode": False}).encode(),
                                                  "fake-signature"), 400)
            captured["retrieved_session"] = {
                **event["data"]["object"], "object": "checkout.session", "livemode": True,
                "payment_status": "unpaid",
            }
            forged = {**event, "id": "evt_liveforged123"}
            captured["retrieved_event"] = {**forged, "object": "event"}
            assert provider.webhook(json.dumps(forged).encode(), "fake-signature")["status"] == "pending"
            assert store.summary("buyer")["balance"] == 800
            captured["retrieved_event"] = {**event, "object": "event"}
            expect_error(lambda: provider.webhook(json.dumps(forged).encode(),
                                                  "fake-signature"), 409)
            captured["retrieved_event"] = {**forged, "object": "event"}
            captured["retrieved_session"]["id"] = "cs_live_other"
            expect_error(lambda: provider.webhook(json.dumps(forged).encode(),
                                                  "fake-signature"), 409)
            assert store.summary("buyer")["balance"] == 800
            captured["retrieved_session"] = {
                **event["data"]["object"], "object": "checkout.session", "livemode": True,
            }
            captured["retrieved_event"] = {**event, "object": "event"}
            assert provider.webhook(json.dumps(event).encode(), "fake-signature")["status"] == "paid"
            assert store.summary("buyer")["balance"] == 3800
            captured["retrieved_refund"] = {
                "id": "re_live123", "object": "refund",
                "payment_intent": "pi_live_123", "amount": 990,
                "status": "pending", "currency": "cny",
            }
            refund_event = {"id": "evt_liverefund123", "livemode": True,
                            "type": "refund.updated", "data": {"object": {
                                **captured["retrieved_refund"], "status": "succeeded"}}}
            captured["retrieved_event"] = {**refund_event, "object": "event"}
            assert provider.webhook(json.dumps(refund_event).encode(),
                                    "fake-signature")["status"] == "refund_not_succeeded"
            assert store.summary("buyer")["balance"] == 3800
            captured["retrieved_refund"]["status"] = "succeeded"
            refund_event["id"] = "evt_liverefund456"
            captured["retrieved_event"] = {**refund_event, "object": "event"}
            assert provider.webhook(json.dumps(refund_event).encode(),
                                    "fake-signature")["status"] == "refunded"
            assert store.summary("buyer")["balance"] == 800

        with patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "sk_live_not_real", "STRIPE_WEBHOOK_SECRET": "whsec_not_real",
            "STRIPE_LIVE_ENABLED": "1", "PUBLIC_ORIGIN": "http://127.0.0.1:8877",
        }):
            assert not StripePaymentProvider(store).configured
        with patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "rk_live_not_real", "STRIPE_WEBHOOK_SECRET": "whsec_not_real",
            "STRIPE_LIVE_ENABLED": "1", "PUBLIC_ORIGIN": "https://rightthesis.com",
        }):
            restricted = StripePaymentProvider(store)
            assert restricted.live
            assert restricted.configured is (restricted.stripe is not None)
        with patch.dict(os.environ, {
            "STRIPE_SECRET_KEY": "rk_test_not_real", "STRIPE_WEBHOOK_SECRET": "whsec_not_real",
            "STRIPE_LIVE_ENABLED": "0", "PUBLIC_ORIGIN": "http://127.0.0.1:8877",
        }):
            restricted_test = StripePaymentProvider(store)
            assert not restricted_test.live
            assert restricted_test.configured is (restricted_test.stripe is not None)


def test_full_refund_revokes_unused_credits_and_handles_event_order():
    with tempfile.TemporaryDirectory() as folder:
        store = BillingStore(Path(folder) / "billing.sqlite3")
        order = store.prepare_stripe_checkout("buyer", "pack_3k", "checkout_refund_001",
                                              livemode=True)
        store.attach_stripe_checkout(order["id"], "cs_live_refund001",
                                     "https://checkout.stripe.com/c/pay/refund001",
                                     int(time.time()) + 3600)
        refund = {"id": "re_refund001", "payment_intent": "pi_refund001",
                  "amount": 990, "status": "succeeded", "currency": "cny"}
        assert store.apply_stripe_succeeded_refund("evt_refund001", "hash-refund", refund)["status"] == "pending_order"
        session = {"id": "cs_live_refund001", "client_reference_id": order["id"],
                   "metadata": {"order_id": order["id"], "account_id": "buyer",
                                "product_id": "pack_3k"},
                   "mode": "payment", "currency": "cny", "amount_total": 990,
                   "payment_status": "paid", "payment_intent": "pi_refund001"}
        assert store.apply_stripe_checkout_event("evt_paidrefund001", "hash-paid", session)["status"] == "refunded"
        assert store.order("buyer", order["id"])["status"] == "refunded"
        assert store.summary("buyer")["balance"] == 800
        assert store.apply_stripe_succeeded_refund("evt_refund001", "hash-refund", refund)["status"] == "duplicate"
        assert len([entry for entry in store.ledger("buyer") if entry["kind"] == "refund"]) == 1

        second = store.prepare_stripe_checkout("buyer", "pack_10k", "checkout_refund_002",
                                               livemode=True)
        store.attach_stripe_checkout(second["id"], "cs_live_refund002",
                                     "https://checkout.stripe.com/c/pay/refund002",
                                     int(time.time()) + 3600)
        second_session = {**session, "id": "cs_live_refund002",
                          "client_reference_id": second["id"], "amount_total": 2990,
                          "payment_intent": "pi_refund002",
                          "metadata": {**session["metadata"], "order_id": second["id"],
                                       "product_id": "pack_10k"}}
        assert store.apply_stripe_checkout_event("evt_paidrefund002", "hash-paid2", second_session)["status"] == "paid"
        assert store.summary("buyer")["balance"] == 10_800
        partial = {"id": "re_partial002", "payment_intent": "pi_refund002", "amount": 1000,
                   "status": "succeeded", "currency": "cny"}
        assert store.apply_stripe_succeeded_refund("evt_partial002", "hash-partial", partial)["status"] == "partially_refunded"
        assert store.summary("buyer")["balance"] == 10_800 - 10_000 * 1000 // 2990
        assert store.order("buyer", second["id"])["refunded_fen"] == 1000
        assert store.apply_stripe_succeeded_refund("evt_partial002", "hash-partial", partial)["status"] == "duplicate"
        full = {**partial, "id": "re_full002", "amount": 1990}
        assert store.apply_stripe_succeeded_refund("evt_full002", "hash-full", full)["status"] == "refunded"
        assert store.summary("buyer")["balance"] == 800
        assert store.order("buyer", second["id"])["status"] == "refunded"

        third = store.prepare_stripe_checkout("buyer", "pack_3k", "checkout_refund_003",
                                              livemode=True)
        store.attach_stripe_checkout(third["id"], "cs_live_refund003",
                                     "https://checkout.stripe.com/c/pay/refund003",
                                     int(time.time()) + 3600)
        third_session = {**session, "id": "cs_live_refund003",
                         "client_reference_id": third["id"], "payment_intent": "pi_refund003",
                         "metadata": {**session["metadata"], "order_id": third["id"]}}
        store.apply_stripe_checkout_event("evt_paidrefund003", "hash-paid3", third_session)
        store.reserve("buyer", "job-refund-003", "x" * 1000, "conservative")
        assert store.summary("buyer")["balance"] == 2800
        third_refund = {"id": "re_refund003", "payment_intent": "pi_refund003",
                        "amount": 990, "status": "succeeded", "currency": "cny"}
        assert store.apply_stripe_succeeded_refund("evt_refund003", "hash-refund3",
                                                   third_refund)["status"] == "refunded"
        assert store.summary("buyer")["balance"] == 800
        released = store.finalize("job-refund-003", success=False)
        assert released["released"] == 0
        assert store.finalize("job-refund-003", success=False)["released"] == 0
        assert store.summary("buyer")["balance"] == 800
        release_entry = next(entry for entry in store.ledger("buyer")
                             if entry["reference"] == "job:job-refund-003"
                             and entry["kind"] == "release")
        assert release_entry["delta"] == 0
        assert release_entry["balance_after"] == 800
        assert release_entry["metadata"]["expired_or_revoked_credits"] == 1000


def test_partial_refund_during_reservation_cannot_reissue_refunded_credits():
    with tempfile.TemporaryDirectory() as folder:
        store = BillingStore(Path(folder) / "billing.sqlite3")
        order = store.prepare_stripe_checkout("buyer", "pack_3k", "partial_reserved_001",
                                              livemode=True)
        store.attach_stripe_checkout(order["id"], "cs_live_partial_reserved",
                                     "https://checkout.stripe.com/c/pay/partial",
                                     int(time.time()) + 3600)
        session = {"id": "cs_live_partial_reserved", "client_reference_id": order["id"],
                   "metadata": {"order_id": order["id"], "account_id": "buyer",
                                "product_id": "pack_3k"},
                   "mode": "payment", "currency": "cny", "amount_total": 990,
                   "payment_status": "paid", "payment_intent": "pi_partial_reserved"}
        store.apply_stripe_checkout_event("evt_partialpaid", "hash-paid", session)
        store.reserve("buyer", "job-partial", "x" * 2000, "conservative")
        assert store.summary("buyer")["balance"] == 1800
        refund = {"id": "re_partial_reserved", "payment_intent": "pi_partial_reserved",
                  "amount": 495, "status": "succeeded", "currency": "cny"}
        assert store.apply_stripe_succeeded_refund(
            "evt_partialrefund", "hash-refund", refund)["status"] == "partially_refunded"
        # The paid grant now has only 1,500 credits; 2,000 are reserved, so
        # none of its unreserved credits may be spent meanwhile.
        assert store.summary("buyer")["balance"] == 800
        released = store.finalize("job-partial", success=False)
        assert released["released"] == 1500
        assert store.summary("buyer")["balance"] == 2300
        assert store.apply_stripe_checkout_event(
            "evt_partialpaidagain", "hash-paid-again", session)["status"] == "partially_refunded"
        assert store.summary("buyer")["balance"] == 2300


def test_checkout_failure_expiry_and_late_paid_webhook():
    clock = [1_700_000_000]
    with tempfile.TemporaryDirectory() as folder:
        store = BillingStore(Path(folder) / "billing.sqlite3", now=lambda: clock[0])
        orphan = store.prepare_stripe_checkout("buyer", "pack_3k", "checkout_orphan_001")
        clock[0] += 30 * 60 + 1
        assert store.order("buyer", orphan["id"])["status"] == "failed"

        order = store.prepare_stripe_checkout("buyer", "pack_3k", "checkout_expired_001")
        store.attach_stripe_checkout(order["id"], "cs_test_latepaid",
                                     "https://checkout.stripe.com/c/pay/latepaid",
                                     clock[0] + 3600)
        clock[0] += 3600
        assert store.order("buyer", order["id"])["status"] == "expired"
        assert store.orders("buyer")[0]["status"] == "expired"
        session = {
            "id": "cs_test_latepaid", "client_reference_id": order["id"],
            "metadata": {"order_id": order["id"], "account_id": "buyer",
                         "product_id": "pack_3k"},
            "mode": "payment", "currency": "cny", "amount_total": 990,
            "payment_status": "paid", "payment_intent": "pi_latepaid",
        }
        assert store.apply_stripe_checkout_event("evt_latepaid", "hash-latepaid", session)["status"] == "paid"
        assert store.order("buyer", order["id"])["status"] == "paid"
        assert store.summary("buyer")["balance"] == 3800

        failing = SimpleNamespace(
            StripeClient=lambda _key: SimpleNamespace(v1=SimpleNamespace(
                checkout=SimpleNamespace(sessions=SimpleNamespace(
                    create=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))))),
        )
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_not_real",
                                  "STRIPE_WEBHOOK_SECRET": "whsec_not_real",
                                  "STRIPE_LIVE_ENABLED": "0"}):
            provider = StripePaymentProvider(store)
            provider.stripe = failing
            provider.configured = True
            expect_error(lambda: provider.checkout("buyer", "pack_3k", "checkout_failed_001",
                                                   origin="http://127.0.0.1:8877",
                                                   customer_email="buyer@example.com"), 502)
        assert store.orders("buyer")[0]["status"] == "failed"

        # A concurrent request may have received the same Stripe session even
        # after the first request timed out; attaching it safely restores pending.
        failed_id = store.orders("buyer")[0]["order_id"]
        store.attach_stripe_checkout(failed_id, "cs_test_recovered",
                                     "https://checkout.stripe.com/c/pay/recovered",
                                     clock[0] + 3600)
        assert store.order("buyer", failed_id)["status"] == "pending"


def test_real_sdk_rejects_bad_signature_when_installed():
    if importlib.util.find_spec("stripe") is None:
        return
    with tempfile.TemporaryDirectory() as folder:
        store = BillingStore(Path(folder) / "billing.sqlite3")
        order = store.prepare_stripe_checkout("buyer", "pack_3k", "checkout_test_004")
        store.attach_stripe_checkout(order["id"], "cs_test_signed",
                                     "https://checkout.stripe.com/c/pay/signed",
                                     int(time.time()) + 3600)
        with patch.dict(os.environ, {"STRIPE_SECRET_KEY": "sk_test_not_real",
                                  "STRIPE_WEBHOOK_SECRET": "whsec_not_real"}):
            provider = StripePaymentProvider(store)
            assert provider.configured
            event = {"id": "evt_signed123", "object": "event", "livemode": False,
                     "type": "checkout.session.completed", "data": {"object": {
                         "id": "cs_test_signed", "client_reference_id": order["id"],
                         "metadata": {"order_id": order["id"], "account_id": "buyer",
                                      "product_id": "pack_3k"},
                         "mode": "payment", "currency": "cny", "amount_total": 990,
                         "payment_status": "paid"}}}
            raw = json.dumps(event, separators=(",", ":")).encode()
            timestamp = int(time.time())
            digest = hmac.new(
                b"whsec_not_real", str(timestamp).encode() + b"." + raw,
                hashlib.sha256).hexdigest()
            signature = f"t={timestamp},v1={digest}"
            expect_error(lambda: provider.webhook(raw, "t=1,v1=bad"), 400)
            assert store.summary("buyer")["balance"] == 800
            assert provider.webhook(raw, signature)["status"] == "paid"
            assert provider.webhook(raw, signature)["status"] == "duplicate"
            assert store.summary("buyer")["balance"] == 3800


def test_http_webhook_without_browser_cookie_when_sdk_installed():
    if importlib.util.find_spec("stripe") is None:
        return
    sys.path.insert(0, str(ROOT / "tests"))
    from http_test_utils import free_port, opener_with_cookies, stop_server, wait_until_ready
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "billing.sqlite3"
        store = BillingStore(database)
        order = store.prepare_stripe_checkout("buyer", "pack_3k", "checkout_test_005")
        store.attach_stripe_checkout(order["id"], "cs_test_http",
                                     "https://checkout.stripe.com/c/pay/http",
                                     int(time.time()) + 3600)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "AUTH_MODE": "accounts", "TRIAL_MODE": "0", "PUBLIC_ORIGIN": base,
            "GOOGLE_OAUTH_REDIRECT_URI": base + "/api/auth/google/callback",
            "AUTH_SESSION_SECRET": "stripe-test-session-secret-more-than-32-bytes",
            "AUTH_EMAIL_DELIVERY": "console", "BILLING_DB": str(database),
            "PAYMENT_PROVIDER": "stripe", "STRIPE_SECRET_KEY": "sk_test_not_real",
            "STRIPE_WEBHOOK_SECRET": "whsec_not_real", "BROWSER": "/usr/bin/true",
        })
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "web/server.py"), str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        opener, _ = opener_with_cookies()
        try:
            wait_until_ready(opener, base, proc)
            event = {"id": "evt_http123", "object": "event", "livemode": False,
                     "type": "checkout.session.completed", "data": {"object": {
                         "id": "cs_test_http", "client_reference_id": order["id"],
                         "metadata": {"order_id": order["id"], "account_id": "buyer",
                                      "product_id": "pack_3k"},
                         "mode": "payment", "currency": "cny", "amount_total": 990,
                         "payment_status": "paid"}}}
            raw = json.dumps(event, separators=(",", ":")).encode()
            timestamp = int(time.time())
            digest = hmac.new(b"whsec_not_real", str(timestamp).encode() + b"." + raw,
                              hashlib.sha256).hexdigest()

            def send(signature):
                request = urllib.request.Request(
                    base + "/api/billing/stripe/webhook", data=raw, method="POST",
                    headers={"Content-Type": "application/json", "Stripe-Signature": signature})
                try:
                    with opener.open(request, timeout=5) as response:
                        return response.status
                except urllib.error.HTTPError as exc:
                    return exc.code

            assert send("t=1,v1=invalid") == 400
            assert store.summary("buyer")["balance"] == 800
            signature = f"t={timestamp},v1={digest}"
            assert send(signature) == 200
            assert send(signature) == 200
            assert store.summary("buyer")["balance"] == 3800
        finally:
            stop_server(proc)


if __name__ == "__main__":
    test_stripe_order_and_webhook_idempotency()
    test_live_reconciliation_repairs_missed_webhooks_without_double_grants()
    test_provider_modes_and_checkout_options()
    test_live_mode_requires_opt_in_https_and_matching_webhook()
    test_full_refund_revokes_unused_credits_and_handles_event_order()
    test_partial_refund_during_reservation_cannot_reissue_refunded_credits()
    test_checkout_failure_expiry_and_late_paid_webhook()
    test_real_sdk_rejects_bad_signature_when_installed()
    test_http_webhook_without_browser_cookie_when_sdk_installed()
    print("✓ Stripe 离线合同：测试密钥、动态支付方式、金额验核和幂等发放")

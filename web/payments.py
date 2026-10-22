"""Payment providers. Live Stripe Checkout requires an explicit server opt-in."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
from typing import Dict
from urllib.parse import quote, urlparse

from billing import BillingError, BillingStore


class PaymentProvider:
    name = "unknown"
    display_name = "未知通道"
    live = False
    configured = False

    def __init__(self, store: BillingStore):
        self.store = store

    def public_status(self) -> Dict:
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "configured": self.configured,
            "live": self.live and self.configured,
            "notice": "支付通道尚未配置。",
        }

    def checkout(self, account_id: str, product_id: str,
                 idempotency_key: str, origin: str = "",
                 customer_email: str = "") -> Dict:
        raise BillingError(
            f"{self.display_name} 尚未配置，当前不能收款。",
            503,
            {"provider": self.name, "configured": False, "live": False},
        )


class MockPaymentProvider(PaymentProvider):
    name = "mock"
    display_name = "本地模拟支付"
    configured = True
    live = False

    def public_status(self) -> Dict:
        status = super().public_status()
        status["notice"] = "本地模拟支付：只测试套餐与额度流程，不会扣款。"
        return status

    def checkout(self, account_id: str, product_id: str,
                 idempotency_key: str, origin: str = "",
                 customer_email: str = "") -> Dict:
        result = self.store.mock_checkout(account_id, product_id, idempotency_key)
        result.update({
            "live": False,
            "notice": "模拟支付已完成，未发生真实扣款。",
        })
        return result


class StripePaymentProvider(PaymentProvider):
    name = "stripe"
    display_name = "Stripe Checkout"

    def __init__(self, store: BillingStore):
        super().__init__(store)
        self.secret_key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
        self.refund_secret_key = os.environ.get("STRIPE_REFUND_SECRET_KEY", "").strip()
        self.webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
        # A restricted key limits damage if the application server is compromised.
        self.live = self.secret_key.startswith(("sk_live_", "rk_live_"))
        self.live_enabled = os.environ.get("STRIPE_LIVE_ENABLED", "").strip() == "1"
        self.public_origin = os.environ.get("PUBLIC_ORIGIN", "").strip().rstrip("/")
        try:
            self.stripe = importlib.import_module("stripe")
        except ImportError:
            self.stripe = None
        mode_allowed = (
            (self.live and self.live_enabled
             and urlparse(self.public_origin).scheme == "https")
            or (self.secret_key.startswith(("sk_test_", "rk_test_"))
                and not self.live_enabled)
        )
        self.configured = bool(mode_allowed and self.webhook_secret.startswith("whsec_")
                               and self.stripe)
        # A separate restricted key grants only the refund write action. The
        # checkout/reconciliation key remains read-only for refund objects.
        self.refund_enabled = bool(self.configured and self.live and
                                   self.refund_secret_key.startswith("rk_live_"))

    def public_status(self) -> Dict:
        status = super().public_status()
        status.update({
            "live": self.live and self.configured,
            "checkout_enabled": self.configured,
            "refund_enabled": self.refund_enabled,
            "payment_methods": ["card", "wechat_pay", "alipay"],
            "notice": ("Stripe 正式收款：银行卡、微信支付、支付宝以收银台实际可用选项为准。"
                       if self.configured and self.live else
                       "Stripe 测试模式：银行卡、微信支付、支付宝；不会真实扣款。"
                       if self.configured else
                       "Stripe 收银台尚未启用；请在服务端配置匹配环境的密钥和回调。"),
        })
        return status

    def checkout(self, account_id: str, product_id: str,
                 idempotency_key: str, origin: str = "",
                 customer_email: str = "") -> Dict:
        if not self.configured:
            return super().checkout(account_id, product_id, idempotency_key)
        parsed = urlparse(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or (parsed.scheme == "http" and parsed.hostname not in
                    {"127.0.0.1", "localhost", "::1"})):
            raise BillingError("支付返回地址必须是可信的 HTTPS 或本机地址", 400)
        if self.live and origin != self.public_origin:
            raise BillingError("正式支付返回地址与站点域名不一致", 400)
        if not isinstance(customer_email, str) or not customer_email:
            raise BillingError("账号缺少已验证邮箱，请重新登录后再试", 403)
        order = self.store.prepare_stripe_checkout(
            account_id, product_id, idempotency_key, livemode=self.live)
        now = int(self.store._now())
        if order["status"] != "pending":
            raise BillingError("订单已处理，请刷新额度页面", 409)
        if order["checkout_url"]:
            if order["checkout_expires_at"] and order["checkout_expires_at"] <= now:
                raise BillingError("收银台链接已过期，请重新下单", 409)
            return {"order_id": order["id"], "status": order["status"],
                    "provider": "stripe", "checkout_url": order["checkout_url"],
                    "reused": True, "live": self.live}
        snapshot = json.loads(order["product_snapshot_json"])
        back = f"{origin}/#/checkout/pro?order={quote(order['id'], safe='')}"
        params = {
            "mode": "payment",
            "customer_email": customer_email,
            # Use the payment methods enabled in the Stripe Dashboard. An
            # explicit allowlist bypasses those dynamic Checkout settings.
            "line_items": [{"price_data": {
                "currency": order["currency"].lower(),
                "unit_amount": order["amount_fen"],
                "product_data": {"name": snapshot["name"]},
            }, "quantity": 1}],
            "client_reference_id": order["id"],
            "metadata": {"order_id": order["id"], "account_id": account_id,
                         "product_id": product_id},
            "success_url": back + "&result=return",
            "cancel_url": back + "&result=cancel",
        }
        try:
            client = self.stripe.StripeClient(self.secret_key)
            session = client.v1.checkout.sessions.create(
                params=params, options={"idempotency_key": "rightthesis-" + order["id"]})
        except Exception as exc:
            self.store.fail_stripe_checkout(order["id"])
            raise BillingError("Stripe 暂时无法创建收银台，请稍后重试", 502) from exc
        if hasattr(session, "to_dict"):
            session = session.to_dict()
        if not isinstance(session, dict):
            self.store.fail_stripe_checkout(order["id"])
            raise BillingError("Stripe 返回了无效的收银台链接", 502)
        session_id = session.get("id")
        checkout_url = session.get("url")
        expires_at = session.get("expires_at")
        expected_prefix = "cs_live_" if self.live else "cs_test_"
        if (not isinstance(session_id, str) or not session_id.startswith(expected_prefix)
                or not isinstance(checkout_url, str)
                or urlparse(checkout_url).scheme != "https"
                or urlparse(checkout_url).hostname != "checkout.stripe.com"
                or not isinstance(expires_at, int)):
            self.store.fail_stripe_checkout(order["id"])
            raise BillingError("Stripe 返回了无效的收银台链接", 502)
        self.store.attach_stripe_checkout(
            order["id"], session_id, checkout_url, expires_at)
        return {"order_id": order["id"], "status": "pending",
                "provider": "stripe", "checkout_url": checkout_url,
                "reused": False, "live": self.live}

    def webhook(self, raw_body: bytes, signature: str) -> Dict:
        if not self.configured:
            raise BillingError("Stripe 支付尚未配置", 503)
        try:
            event = self.stripe.Webhook.construct_event(
                raw_body, signature, self.webhook_secret)
        except (ValueError, self.stripe.error.SignatureVerificationError) as exc:
            raise BillingError("Stripe 回调签名无效", 400) from exc
        if hasattr(event, "to_dict"):
            event = event.to_dict()
        if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
            raise BillingError("Stripe 回调结构无效", 400)
        if event.get("livemode") is not self.live:
            raise BillingError("Stripe 回调环境与收银台环境不一致", 400)
        event_type = event.get("type")
        supported = {"refund.created", "refund.updated", "refund.failed",
                     "checkout.session.completed", "checkout.session.async_payment_succeeded"}
        if event_type not in supported:
            return {"status": "ignored"}
        if self.live:
            event = self._retrieve_live_event(event)
            event_type = event["type"]
            payload_hash = hashlib.sha256(json.dumps(
                event, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        else:
            payload_hash = hashlib.sha256(raw_body).hexdigest()
        if event_type in {"refund.created", "refund.updated", "refund.failed"}:
            refund = event.get("data", {}).get("object", {})
            if not isinstance(refund, dict):
                raise BillingError("Stripe 退款回调结构无效", 400)
            if self.live:
                refund = self._retrieve_live_object("refund", refund.get("id"))
            return self.store.apply_stripe_succeeded_refund(
                event.get("id"), payload_hash,
                refund)
        session = event.get("data", {}).get("object", {})
        if not isinstance(session, dict):
            raise BillingError("Stripe 收银台回调结构无效", 400)
        if self.live:
            session = self._retrieve_live_object("session", session.get("id"))
        return self.store.apply_stripe_checkout_event(
            event.get("id"), payload_hash, session)

    @staticmethod
    def _reconciliation_event_id(kind: str, object_id: str) -> str:
        # A stable internal event ID makes a missed webhook and a subsequent
        # authenticated Stripe fetch safe to process in either order.
        return "evt_" + hashlib.sha256(f"rightthesis:{kind}:{object_id}".encode()).hexdigest()[:32]

    @staticmethod
    def _listed_objects(response: object) -> tuple[list, bool]:
        if hasattr(response, "to_dict"):
            response = response.to_dict()
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise BillingError("Stripe 对账列表格式无效", 502)
        return response["data"], response.get("has_more") is True

    def reconcile_order(self, account_id: str, order_id: str,
                        *, audit_refunds: bool = False) -> Dict:
        """Repair missed Checkout webhooks using Stripe's live object API.

        This method only accepts an account-owned order ID. It never trusts a
        browser-supplied session, amount, or payment state.
        """
        order = self.store.stripe_order_for_reconciliation(account_id, order_id)
        if not order:
            raise BillingError("订单不存在", 404)
        if not self.configured or not self.live or not order["stripe_livemode"]:
            return {"status": "not_live"}
        session_id = order["provider_order_id"]
        if order["status"] in {"pending", "expired"} and session_id:
            session = self._retrieve_live_object("session", session_id)
            if session.get("payment_status") == "paid":
                intent = session.get("payment_intent")
                if isinstance(intent, str) and intent.startswith("pi_"):
                    # Record refunds before the grant. If the refund webhook
                    # was missed, the grant is reduced in the same transaction.
                    self.reconcile_refunds(intent)
                digest = hashlib.sha256(json.dumps(
                    session, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                self.store.apply_stripe_checkout_event(
                    self._reconciliation_event_id("session", session_id), digest, session)
        if audit_refunds:
            updated = self.store.stripe_order_for_reconciliation(account_id, order_id)
            payment_intent = updated["payment_intent_id"] if updated else None
            if payment_intent:
                self.reconcile_refunds(payment_intent)
        return {"status": "checked"}

    def reconcile_refunds(self, payment_intent_id: str) -> Dict:
        if not re.fullmatch(r"pi_[A-Za-z0-9]+", payment_intent_id):
            raise BillingError("Stripe PaymentIntent 无效", 400)
        client = self.stripe.StripeClient(self.secret_key)
        last_id = None
        pending_amount = 0
        succeeded_amount = 0
        for _ in range(100):
            params = {"payment_intent": payment_intent_id, "limit": 100}
            if last_id:
                params["starting_after"] = last_id
            try:
                response = client.v1.refunds.list(params=params)
            except Exception as exc:
                raise BillingError("Stripe 退款对账暂不可用", 502) from exc
            refunds, has_more = self._listed_objects(response)
            if has_more and not refunds:
                raise BillingError("Stripe 退款分页结果无效", 502)
            for item in refunds:
                refund_id = item.get("id") if isinstance(item, dict) else None
                refund = self._retrieve_live_object("refund", refund_id)
                if refund.get("payment_intent") != payment_intent_id:
                    raise BillingError("Stripe 退款与订单不匹配", 409)
                if (refund.get("status") not in {"pending", "requires_action", "succeeded",
                                                 "failed", "canceled"}
                        or not isinstance(refund.get("amount"), int)
                        or isinstance(refund.get("amount"), bool)
                        or refund["amount"] <= 0):
                    raise BillingError("Stripe 退款状态或金额无效，已停止新退款", 409)
                digest = hashlib.sha256(json.dumps(
                    refund, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                self.store.apply_stripe_succeeded_refund(
                    self._reconciliation_event_id("refund", refund_id + ":" + digest),
                    digest, refund)
                if refund.get("status") in {"pending", "requires_action"}:
                    pending_amount += int(refund.get("amount") or 0)
                elif refund.get("status") == "succeeded":
                    succeeded_amount += int(refund.get("amount") or 0)
            if not has_more:
                return {"pending_fen": pending_amount,
                        "succeeded_fen": succeeded_amount}
            last_id = refunds[-1]["id"]
        raise BillingError("Stripe 退款分页超出安全上限，需人工核对", 502)

    def issue_admin_refund(self, order_id: str, actor_account_id: str,
                           amount_fen: int, reason: str, note: str,
                           attempt_id: str) -> Dict:
        """Issue one live refund only after local and Stripe reconciliation."""
        if not self.refund_enabled:
            raise BillingError("管理员退款尚未配置独立的 Stripe 退款密钥", 503)
        existing = self.store.admin_refund_attempt(attempt_id)
        if existing:
            return self.store.begin_admin_refund(order_id, actor_account_id,
                                                 amount_fen, reason, note,
                                                 attempt_id, 0)
        order = self.store.admin_refund_order(order_id)
        if not order:
            raise BillingError("订单不存在", 404)
        if (order["provider"] != "stripe" or not order["stripe_livemode"]
                or order["status"] not in {"paid", "partially_refunded"}
                or not isinstance(order["payment_intent_id"], str)):
            raise BillingError("此订单不能从管理后台发起退款", 409)
        payment_intent = order["payment_intent_id"]
        provider_totals = self.reconcile_refunds(payment_intent)
        if provider_totals["pending_fen"]:
            raise BillingError("Stripe 尚有处理中退款，请先等待结果", 409)
        if self.unresolved_disputes(payment_intent):
            raise BillingError("订单存在未解决的支付争议，请先在 Stripe 核对", 409)
        order = self.store.admin_refund_order(order_id)
        if provider_totals["succeeded_fen"] != int(order["refunded_fen"]):
            raise BillingError("Stripe 与本地退款金额不一致，请先核对", 409)
        attempt = self.store.begin_admin_refund(
            order_id, actor_account_id, amount_fen, reason, note,
            attempt_id, provider_totals["succeeded_fen"])
        if attempt["reused"]:
            return attempt
        params = {"payment_intent": payment_intent, "amount": amount_fen,
                  "reason": reason, "metadata": {
                      "rightthesis_order_id": order_id,
                      "rightthesis_refund_attempt": attempt_id}}
        try:
            response = self.stripe.StripeClient(self.refund_secret_key).v1.refunds.create(
                params=params, options={"idempotency_key": "rightthesis-refund-" + attempt_id})
        except Exception as exc:
            # Timeouts are ambiguous: a refund may have reached Stripe. Keep
            # the order locked instead of issuing another request with a new ID.
            rejected = getattr(exc, "http_status", None) in {400, 401, 403}
            self.store.update_admin_refund_attempt(
                attempt_id, "failed" if rejected else "unknown")
            raise BillingError(
                "Stripe 拒绝退款请求；请检查退款密钥权限与订单状态" if rejected else
                "Stripe 退款结果暂不确定，请在 Stripe 核对，勿再次提交",
                409 if rejected else 502, {"attempt_id": attempt_id}) from exc
        if hasattr(response, "to_dict"):
            response = response.to_dict()
        if (not isinstance(response, dict) or response.get("object") != "refund"
                or not isinstance(response.get("id"), str)
                or not response["id"].startswith("re_")
                or response.get("payment_intent") != payment_intent
                or response.get("amount") != amount_fen
                or str(response.get("currency", "")).upper() != order["currency"]):
            self.store.update_admin_refund_attempt(attempt_id, "unknown")
            raise BillingError("Stripe 退款响应不完整，请在 Stripe 核对，勿再次提交",
                               502, {"attempt_id": attempt_id})
        refund_id = response["id"]
        state = response.get("status")
        if state not in {"pending", "requires_action", "succeeded", "failed", "canceled"}:
            self.store.update_admin_refund_attempt(attempt_id, "unknown", refund_id)
            raise BillingError("Stripe 退款状态不明确，请在 Stripe 核对，勿再次提交",
                               502, {"attempt_id": attempt_id})
        if state in {"failed", "canceled"}:
            return self.store.update_admin_refund_attempt(attempt_id, "failed", refund_id)
        attempt = self.store.update_admin_refund_attempt(attempt_id, "submitted", refund_id)
        try:
            self.reconcile_refunds(payment_intent)
        except BillingError:
            # The hourly reconciliation job and signed webhook can finish this.
            return attempt
        return self.store.admin_refund_attempt(attempt_id)

    def unresolved_disputes(self, payment_intent_id: str) -> list[str]:
        if not re.fullmatch(r"pi_[A-Za-z0-9]+", payment_intent_id):
            raise BillingError("Stripe PaymentIntent 无效", 400)
        try:
            response = self.stripe.StripeClient(self.secret_key).v1.disputes.list(
                params={"payment_intent": payment_intent_id, "limit": 100})
        except Exception as exc:
            raise BillingError("Stripe 争议对账暂不可用", 502) from exc
        disputes, has_more = self._listed_objects(response)
        if has_more:
            raise BillingError("Stripe 争议超过单页上限，需人工核对", 502)
        return [item["id"] for item in disputes if isinstance(item, dict)
                and item.get("status") not in {"won", "warning_closed"}]

    def _retrieve_live_event(self, signed_event: Dict) -> Dict:
        event_id = signed_event.get("id")
        signed_object = signed_event.get("data", {}).get("object")
        if (not isinstance(event_id, str)
                or not re.fullmatch(r"evt_[A-Za-z0-9]+", event_id)
                or not isinstance(signed_object, dict)
                or not isinstance(signed_object.get("id"), str)):
            raise BillingError("Stripe 回调事件字段无效", 400)
        try:
            event = self.stripe.StripeClient(self.secret_key).v1.events.retrieve(event_id)
        except Exception as exc:
            raise BillingError("暂时无法向 Stripe 核验事件", 502) from exc
        if hasattr(event, "to_dict"):
            event = event.to_dict()
        data = event.get("data") if isinstance(event, dict) else None
        obj = data.get("object") if isinstance(data, dict) else None
        if (not isinstance(event, dict) or event.get("object") != "event"
                or event.get("id") != event_id or event.get("livemode") is not True
                or event.get("type") != signed_event.get("type")
                or not isinstance(obj, dict)
                or obj.get("id") != signed_object["id"]):
            raise BillingError("Stripe 事件实时核验不匹配", 409)
        return event

    def _retrieve_live_object(self, kind: str, object_id: str) -> Dict:
        """Never grant or revoke credits from a live webhook payload alone.

        A leaked signing secret can authenticate a forged payload.  Fetching the
        actual object with the server's separate API key makes Stripe's current
        payment/refund state authoritative instead of the event body.
        """
        prefix = "cs_live_" if kind == "session" else "re_"
        if (not isinstance(object_id, str) or not object_id.startswith(prefix)
                or not re.fullmatch(r"[A-Za-z0-9_]+", object_id)):
            raise BillingError("Stripe 回调对象 ID 无效", 400)
        try:
            client = self.stripe.StripeClient(self.secret_key)
            if kind == "session":
                obj = client.v1.checkout.sessions.retrieve(object_id)
            else:
                obj = client.v1.refunds.retrieve(object_id)
        except Exception as exc:
            raise BillingError("暂时无法向 Stripe 核验支付状态", 502) from exc
        if hasattr(obj, "to_dict"):
            obj = obj.to_dict()
        expected_type = "checkout.session" if kind == "session" else "refund"
        if (not isinstance(obj, dict) or obj.get("id") != object_id
                or obj.get("object") != expected_type
                or (kind == "session" and obj.get("livemode") is not True)):
            raise BillingError("Stripe 实时核验结果与正式环境不一致", 409)
        return obj


class EpayPaymentProvider(PaymentProvider):
    name = "epay"
    display_name = "易支付"


class UnknownPaymentProvider(PaymentProvider):
    def __init__(self, store: BillingStore, name: str):
        super().__init__(store)
        self.name = name
        self.display_name = f"未知支付通道 {name}"


def create_payment_provider(name: str, store: BillingStore) -> PaymentProvider:
    normalized = (name or "mock").strip().lower()
    if normalized == "mock":
        return MockPaymentProvider(store)
    if normalized == "stripe":
        return StripePaymentProvider(store)
    if normalized in {"epay", "yipay", "易支付"}:
        return EpayPaymentProvider(store)
    return UnknownPaymentProvider(store, normalized or "unknown")

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
                 idempotency_key: str, origin: str = "") -> Dict:
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
                 idempotency_key: str, origin: str = "") -> Dict:
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

    def public_status(self) -> Dict:
        status = super().public_status()
        status.update({
            "live": self.live and self.configured,
            "checkout_enabled": self.configured,
            "payment_methods": ["card", "wechat_pay", "alipay"],
            "notice": ("Stripe 正式收款：银行卡、微信支付、支付宝以收银台实际可用选项为准。"
                       if self.configured and self.live else
                       "Stripe 测试模式：银行卡、微信支付、支付宝；不会真实扣款。"
                       if self.configured else
                       "Stripe 收银台尚未启用；请在服务端配置匹配环境的密钥和回调。"),
        })
        return status

    def checkout(self, account_id: str, product_id: str,
                 idempotency_key: str, origin: str = "") -> Dict:
        if not self.configured:
            return super().checkout(account_id, product_id, idempotency_key)
        parsed = urlparse(origin)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or (parsed.scheme == "http" and parsed.hostname not in
                    {"127.0.0.1", "localhost", "::1"})):
            raise BillingError("支付返回地址必须是可信的 HTTPS 或本机地址", 400)
        if self.live and origin != self.public_origin:
            raise BillingError("正式支付返回地址与站点域名不一致", 400)
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
        supported = {"refund.created", "refund.updated",
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
        if event_type in {"refund.created", "refund.updated"}:
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

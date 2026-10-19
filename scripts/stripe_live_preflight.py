"""Read-only production Stripe permission check; never prints credentials or data."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import stripe


ROOT = Path(__file__).resolve().parent.parent
NEEDED = {"AUTH_MODE", "PAYMENT_PROVIDER", "PUBLIC_ORIGIN",
          "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"}


def settings() -> dict[str, str]:
    values = {}
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in NEEDED:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key] = value
    return {key: os.environ.get(key, values.get(key, "")) for key in NEEDED}


def main() -> int:
    try:
        config = settings()
    except OSError:
        print("FAIL: 无法读取服务器 .env")
        return 1
    origin = urlparse(config["PUBLIC_ORIGIN"])
    if (config["AUTH_MODE"] != "accounts" or config["PAYMENT_PROVIDER"] != "stripe"
            or origin.scheme != "https" or origin.netloc != "rightthesis.com"
            or not config["STRIPE_SECRET_KEY"].startswith(("rk_live_", "sk_live_"))
            or not config["STRIPE_WEBHOOK_SECRET"].startswith("whsec_")):
        print("FAIL: 正式支付配置不完整或环境不匹配（不会输出密钥）")
        return 1
    client = stripe.StripeClient(config["STRIPE_SECRET_KEY"])
    checks = (
        ("Checkout Sessions 读取", lambda: client.v1.checkout.sessions.list(params={"limit": 1})),
        ("Events 读取", lambda: client.v1.events.list(params={"limit": 1})),
        ("Refunds 读取", lambda: client.v1.refunds.list(params={"limit": 1})),
    )
    for label, check in checks:
        try:
            check()
        except Exception:
            print(f"FAIL: {label}失败；检查密钥权限或服务器到 Stripe 的网络")
            return 1
        print(f"OK: {label}")
    print("OK: 正式只读权限检查通过；尚未发起任何付款")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

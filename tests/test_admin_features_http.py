"""Admin credit grants and aggregate traffic obey account and origin boundaries."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tests"))

from auth import AuthStore  # noqa: E402
from billing import BillingStore  # noqa: E402
from http_test_utils import free_port, opener_with_cookies, request, stop_server, wait_until_ready  # noqa: E402


def run():
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "app.sqlite3"
        billing = BillingStore(database)
        secret = "admin-features-http-secret-at-least-32-bytes"
        auth = AuthStore(database, secret.encode())
        admin = auth.rotate_authenticated(
            auth.create_pre_auth()["token"], provider="google", subject="grant-admin",
            email="admin@example.com",
        )
        user = auth.rotate_authenticated(
            auth.create_pre_auth()["token"], provider="google", subject="grant-user",
            email="recipient@example.com",
        )
        original_balance = billing.summary(user["account_id"])["balance"]
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.update({
            "AUTH_MODE": "accounts", "TRIAL_MODE": "0", "PUBLIC_ORIGIN": base,
            "GOOGLE_OAUTH_REDIRECT_URI": base + "/api/auth/google/callback",
            "AUTH_SESSION_SECRET": secret, "AUTH_EMAIL_DELIVERY": "console",
            "BILLING_DB": str(database), "PAYMENT_PROVIDER": "mock",
            "ADMIN_EMAILS": "admin@example.com", "BROWSER": "/usr/bin/true",
        })
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "web/server.py"), str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=environment,
        )
        opener, _ = opener_with_cookies()
        try:
            wait_until_ready(opener, base, process)
            admin_cookie = {"Cookie": f"rightthesis_session={admin['token']}"}
            user_cookie = {"Cookie": f"rightthesis_session={user['token']}"}
            admin_write = {**admin_cookie, "Origin": base,
                           "X-CSRF-Token": admin["csrf_token"]}
            user_write = {**user_cookie, "Origin": base,
                          "X-CSRF-Token": user["csrf_token"]}

            # Anonymous browsers can report only a predefined route; no
            # cookie, IP, visitor ID or document URL is in the event payload.
            code, _, _ = request(opener, base, "/api/traffic/page-view",
                                 {"path": "/pricing"}, {"Origin": base})
            assert code == 204
            for body, expected in (({"path": "/admin/users"}, 400),
                                   ({"path": "/app/documents/private"}, 400),
                                   ({"path": "/pricing", "visitor_id": "x"}, 400)):
                code, _, _ = request(opener, base, "/api/traffic/page-view",
                                     body, {"Origin": base})
                assert code == expected
            code, _, _ = request(opener, base, "/api/traffic/page-view",
                                 {"path": "/"})
            assert code == 403
            code, _, _ = request(opener, base, "/api/traffic/page-view",
                                 {"path": "/"}, {"Origin": "https://other.example"})
            assert code == 403
            code, _, _ = request(opener, base, "/api/admin/traffic?days=7",
                                 headers=user_cookie)
            assert code == 403
            code, traffic, _ = request(opener, base, "/api/admin/traffic?days=7",
                                       headers=admin_cookie)
            assert code == 200 and traffic["period_views"] == 1
            assert traffic["top_pages"] == [{"path": "/pricing", "views": 1}]
            assert "visitor" not in str(traffic).lower()
            code, _, _ = request(opener, base, "/api/admin/traffic?days=13",
                                 headers=admin_cookie)
            assert code == 400

            target = user["account_id"]
            grant_path = f"/api/admin/users/{target}/credits"
            payload = {"request_id": str(uuid.uuid4()), "confirm_email": "recipient@example.com",
                       "credits": 5000, "valid_days": 90, "reason": "客服补偿发放额度"}
            code, _, _ = request(opener, base, grant_path, payload, admin_cookie)
            assert code == 403, "CSRF and Origin are required"
            code, _, _ = request(opener, base, grant_path, payload, user_write)
            assert code == 403, "ordinary users cannot grant credits"
            code, _, _ = request(opener, base, grant_path,
                                 {**payload, "confirm_email": "wrong@example.com"}, admin_write)
            assert code == 409, "recipient email must match the selected account"
            assert billing.summary(target)["balance"] == original_balance
            code, first, _ = request(opener, base, grant_path, payload, admin_write)
            assert code == 201 and first["grant"]["reused"] is False
            assert first["user"]["balance"] == original_balance + 5000
            assert first["user"]["admin_grants"][0]["reason"] == payload["reason"]
            assert first["user"]["admin_grants"][0]["actor_email"] == "admin@example.com"
            code, again, _ = request(opener, base, grant_path, payload, admin_write)
            assert code == 200 and again["grant"]["reused"] is True
            assert billing.summary(target)["balance"] == original_balance + 5000
        finally:
            stop_server(process)


if __name__ == "__main__":
    run()
    print("✓ 管理员发放与浏览统计 HTTP 权限、幂等和聚合")

"""Account data actions are authenticated, account-scoped and CSRF-protected."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tests"))

from auth import AuthStore  # noqa: E402
from billing import BillingStore  # noqa: E402
from http_test_utils import free_port, opener_with_cookies, request, stop_server, wait_until_ready  # noqa: E402
from workspace_store import WorkspaceStore  # noqa: E402


def run():
    source = ast.parse((ROOT / "web/server.py").read_text(encoding="utf-8"))
    env_keys = next(ast.literal_eval(node.value) for node in source.body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "_LOCAL_ENV_KEYS"
                            for target in node.targets))
    assert "ADMIN_EMAILS" in env_keys
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "app.sqlite3"
        BillingStore(database)
        workspace = WorkspaceStore(database)
        secret = "privacy-http-secret-with-more-than-32-bytes"
        auth = AuthStore(database, secret.encode())
        session = auth.rotate_authenticated(
            auth.create_pre_auth()["token"], provider="google", subject="writer-subject",
            email="writer@example.com",
        )
        another = auth.rotate_authenticated(
            auth.create_pre_auth()["token"], provider="google", subject="other-subject",
            email="other@example.com",
        )
        account = session["account_id"]
        workspace.create_manuscript(account, {
            "name": "Thesis", "kind": "text", "source": "private source text",
            "current": "private current text", "notices": [],
        })
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.update({
            "AUTH_MODE": "accounts", "TRIAL_MODE": "0", "PUBLIC_ORIGIN": base,
            "GOOGLE_OAUTH_REDIRECT_URI": base + "/api/auth/google/callback",
            "AUTH_SESSION_SECRET": secret, "AUTH_EMAIL_DELIVERY": "console",
            "BILLING_DB": str(database), "PAYMENT_PROVIDER": "mock",
            "ADMIN_EMAILS": "writer@example.com",
            "BROWSER": "/usr/bin/true",
        })
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "web/server.py"), str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=environment,
        )
        opener, _ = opener_with_cookies()
        try:
            wait_until_ready(opener, base, process)
            code, config, _ = request(opener, base, "/api/config")
            assert code == 200 and config["admin_read_only_configured"] is True
            cookie = {"Cookie": f"rightthesis_session={session['token']}"}
            code, _, _ = request(opener, base, "/api/account/data-export")
            assert code == 401
            code, exported, headers = request(opener, base, "/api/account/data-export",
                                              headers=cookie)
            assert code == 200
            assert headers["Content-Disposition"].startswith("attachment;")
            assert exported["manuscripts"][0]["source"] == "private source text"
            assert "auth_sessions" not in exported
            code, admin_orders, _ = request(opener, base, "/api/admin/orders", headers=cookie)
            assert code == 200 and "orders" in admin_orders
            code, _, _ = request(opener, base, "/api/admin/orders")
            assert code == 401
            code, _, _ = request(opener, base, "/api/admin/orders", headers={
                "Cookie": f"rightthesis_session={another['token']}"})
            assert code == 403
            code, _, _ = request(opener, base, "/api/account/delete-request",
                                 {"confirm_email": "writer@example.com"}, cookie)
            assert code == 403
            allowed = {**cookie, "Origin": base, "X-CSRF-Token": session["csrf_token"]}
            code, reply, _ = request(opener, base, "/api/account/delete-request",
                                     {"confirm_email": "writer@example.com"}, allowed)
            assert code == 202 and reply["request"]["status"] == "pending"
            code, reply, _ = request(opener, base, "/api/account/privacy-request",
                                     headers=cookie)
            assert code == 200 and reply["request"]["status"] == "pending"
            code, reply, _ = request(opener, base, "/api/account/delete-request/cancel",
                                     {}, allowed)
            assert code == 200 and reply["request"]["status"] == "cancelled"
        finally:
            stop_server(process)


if __name__ == "__main__":
    run()
    print("✓ 账户导出与删除申请 HTTP 身份、范围和 CSRF 校验")

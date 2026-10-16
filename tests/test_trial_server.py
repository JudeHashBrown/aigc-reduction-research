"""Anonymous trial HTTP integration tests on the loopback interface."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from http_test_utils import (  # noqa: E402
    free_port,
    opener_with_cookies,
    request,
    stop_server,
    wait_until_ready,
)


def run():
    with tempfile.TemporaryDirectory() as folder_name:
        folder = Path(folder_name)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        public_origin = "https://writer.private-example.ts.net"
        env = os.environ.copy()
        env.update({
            "AUTH_MODE": "trial",
            "TRIAL_MODE": "1",
            "TRIAL_BIND_HOST": "127.0.0.1",
            "TRIAL_LAN_ORIGIN": "",
            "TRIAL_SESSION_SECRET_FILE": str(folder / "session-secret"),
            "TRIAL_PUBLIC_ORIGIN": public_origin,
            "BILLING_DB": str(folder / "billing.sqlite3"),
            "PAYMENT_PROVIDER": "mock",
            "LLM_BASE_URL": "http://127.0.0.1:9/v1",
            "LLM_API_KEY": "integration-test-only",
            "LLM_MODEL": "offline-test-model",
            "BROWSER": "/usr/bin/true",
        })
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / "web/server.py"), str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        health_client, _ = opener_with_cookies()
        guest_a, jar_a = opener_with_cookies()
        guest_b, _ = opener_with_cookies()
        try:
            wait_until_ready(health_client, base, proc)

            code, session_a, headers_a = request(guest_a, base, "/api/session")
            assert code == 200
            assert set(session_a) == {
                "trial_mode", "authenticated", "user", "csrf_token", "billing",
            }
            assert session_a["trial_mode"] is True
            assert session_a["authenticated"] is True
            assert session_a["user"]["kind"] == "guest"
            assert session_a["billing"]["balance"] == 3000
            account_a = session_a["user"]["account_id"]
            csrf_a = session_a["csrf_token"]
            cookie_header = headers_a.get("Set-Cookie", "")
            assert "HttpOnly" in cookie_header
            assert "SameSite=Strict" in cookie_header
            assert "Secure" not in cookie_header
            assert any(cookie.name == "humanizer_trial_session" for cookie in jar_a)

            code, same_session, _ = request(guest_a, base, "/api/session")
            assert code == 200
            assert same_session["user"]["account_id"] == account_a
            assert same_session["csrf_token"] == csrf_a

            code, session_b, _ = request(guest_b, base, "/api/session")
            assert code == 200
            account_b = session_b["user"]["account_id"]
            csrf_b = session_b["csrf_token"]
            assert account_b != account_a
            code, summary_b, _ = request(guest_b, base, "/api/billing/summary")
            assert code == 200
            assert summary_b["account_id"] == account_b
            assert summary_b["balance"] == 3000

            code, _, _ = request(
                guest_a, base, "/api/v1/analyze", {"text": "测试"},
            )
            assert code == 403
            code, _, _ = request(
                guest_a, base, "/api/v1/analyze", {"text": "测试"},
                {"X-CSRF-Token": csrf_a, "Origin": "https://evil.example"},
            )
            assert code == 403
            code, analysis, _ = request(
                guest_a, base, "/api/v1/analyze",
                {"text": "本文深入探讨了该问题。"},
                {"X-CSRF-Token": csrf_a, "Origin": base},
            )
            assert code == 200 and "summary" in analysis

            code, job, _ = request(
                guest_a, base, "/api/v1/rewrite-jobs",
                {
                    "text": "本文深入探讨了该问题。",
                    "strength": "conservative",
                    "request_id": "anonymous_owner_0001",
                },
                {"X-CSRF-Token": csrf_a, "Origin": base},
            )
            assert code == 200 and job.get("job")
            job_id = job["job"]
            code, _, _ = request(guest_b, base, "/api/job/" + job_id)
            assert code == 404
            code, owned_job, _ = request(guest_a, base, "/api/job/" + job_id)
            assert code == 200 and owned_job["state"] in {"running", "error"}

            code, checkout, _ = request(
                guest_b, base, "/api/billing/checkout",
                {"product_id": "pack_3k", "idempotency_key": "trial_buy_0001"},
                {"X-CSRF-Token": csrf_b, "Origin": base},
            )
            assert code == 403
            assert checkout.get("code") == "trial_checkout_disabled"

            public_client, _ = opener_with_cookies()
            code, public_session, public_headers = request(
                public_client,
                base,
                "/api/session",
                headers={"Host": "writer.private-example.ts.net"},
            )
            assert code == 200 and public_session["authenticated"] is True
            assert "Secure" in public_headers.get("Set-Cookie", "")

            code, _, _ = request(
                guest_a, base, "/api/session",
                headers={"Host": "evil.example"},
            )
            assert code == 403

            safe_write_headers = {"X-CSRF-Token": csrf_a, "Origin": base}
            for removed_path in ("/api/session/login", "/api/session/logout"):
                code, removed, _ = request(
                    guest_a, base, removed_path, {}, safe_write_headers,
                )
                assert code == 410
                assert removed.get("code") == "session_operation_removed"
        finally:
            stop_server(proc)


if __name__ == "__main__":
    run()
    print("✓ 匿名 HTTP：会话、CSRF、Host/Origin、额度与任务隔离全部正确")

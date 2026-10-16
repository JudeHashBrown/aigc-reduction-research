"""LAN-facing anonymous trial and configuration-safety tests."""
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


def assert_bad_config(folder: Path, overrides: dict[str, str], port: int,
                      run_server: bool = False) -> None:
    env = os.environ.copy()
    env.update({
        "AUTH_MODE": "local",
        "TRIAL_MODE": "0",
        "TRIAL_BIND_HOST": "127.0.0.1",
        "TRIAL_LAN_ORIGIN": "",
        "TRIAL_PUBLIC_ORIGIN": "",
        "TRIAL_SESSION_SECRET_FILE": str(folder / "bad-secret"),
        "BILLING_DB": str(folder / "bad-billing.sqlite3"),
        "PAYMENT_PROVIDER": "mock",
        "LLM_BASE_URL": "",
        "LLM_API_KEY": "",
        "LLM_MODEL": "",
        "BROWSER": "/usr/bin/true",
    })
    env.update(overrides)
    env["AUTH_MODE"] = "trial" if env.get("TRIAL_MODE") == "1" else "local"
    if run_server:
        command = [sys.executable, str(ROOT / "web/server.py"), str(port)]
    else:
        command = [
            sys.executable,
            "-c",
            "import sys; "
            f"sys.path.insert(0, {str(ROOT / 'web')!r}); import server",
        ]
    result = subprocess.run(
        command,
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=8,
    )
    assert result.returncode != 0, (overrides, result.stdout, result.stderr)


def run():
    with tempfile.TemporaryDirectory() as folder_name:
        folder = Path(folder_name)
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        lan_origin = f"http://192.168.50.23:{port}"
        lan_host = f"192.168.50.23:{port}"
        public_origin = "https://writer.private-example.ts.net"
        env = os.environ.copy()
        env.update({
            "AUTH_MODE": "trial",
            "TRIAL_MODE": "1",
            "TRIAL_BIND_HOST": "0.0.0.0",
            "TRIAL_LAN_ORIGIN": lan_origin,
            "TRIAL_PUBLIC_ORIGIN": public_origin,
            "TRIAL_SESSION_SECRET_FILE": str(folder / "session-secret"),
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
        lan = {"Host": lan_host}
        lan_write = {"Host": lan_host, "Origin": lan_origin}
        try:
            wait_until_ready(health_client, base, proc)

            code, session_a, headers_a = request(
                guest_a, base, "/api/session", headers=lan,
            )
            assert code == 200 and session_a["authenticated"] is True
            assert session_a["trial_mode"] is True
            assert session_a["user"]["kind"] == "guest"
            assert session_a["billing"]["balance"] == 3000
            account_a = session_a["user"]["account_id"]
            csrf_a = session_a["csrf_token"]
            lan_cookie = headers_a.get("Set-Cookie", "")
            assert "HttpOnly" in lan_cookie and "SameSite=Strict" in lan_cookie
            assert "Secure" not in lan_cookie
            assert any(cookie.name == "humanizer_trial_session" for cookie in jar_a)

            code, same_session, _ = request(
                guest_a, base, "/api/session", headers=lan,
            )
            assert code == 200
            assert same_session["user"]["account_id"] == account_a

            code, session_b, _ = request(
                guest_b, base, "/api/session", headers=lan,
            )
            assert code == 200
            account_b = session_b["user"]["account_id"]
            assert account_b != account_a
            code, summary_b, _ = request(
                guest_b, base, "/api/billing/summary", headers=lan,
            )
            assert code == 200
            assert summary_b["account_id"] == account_b
            assert summary_b["balance"] == 3000

            code, _, _ = request(
                guest_a, base, "/api/v1/analyze", {"text": "测试"}, lan_write,
            )
            assert code == 403
            code, _, _ = request(
                guest_a,
                base,
                "/api/v1/analyze",
                {"text": "测试"},
                {"Host": lan_host, "X-CSRF-Token": csrf_a},
            )
            assert code == 403
            code, _, _ = request(
                guest_a,
                base,
                "/api/v1/analyze",
                {"text": "测试"},
                {
                    "Host": lan_host,
                    "Origin": f"http://192.168.50.24:{port}",
                    "X-CSRF-Token": csrf_a,
                },
            )
            assert code == 403
            code, analysis, _ = request(
                guest_a,
                base,
                "/api/v1/analyze",
                {"text": "本文深入探讨了该问题。"},
                {**lan_write, "X-CSRF-Token": csrf_a},
            )
            assert code == 200 and "summary" in analysis

            code, _, _ = request(
                guest_a,
                base,
                "/api/session",
                headers={"Host": "evil.example"},
            )
            assert code == 403

            public_client, _ = opener_with_cookies()
            code, public_session, public_headers = request(
                public_client,
                base,
                "/api/session",
                headers={"Host": "writer.private-example.ts.net"},
            )
            assert code == 200 and public_session["authenticated"] is True
            assert "Secure" in public_headers.get("Set-Cookie", "")
        finally:
            stop_server(proc)

        assert_bad_config(folder, {
            "TRIAL_MODE": "0",
            "TRIAL_BIND_HOST": "0.0.0.0",
        }, port)
        assert_bad_config(folder, {
            "TRIAL_MODE": "1",
            "TRIAL_BIND_HOST": "0.0.0.0",
            "TRIAL_LAN_ORIGIN": "",
        }, port)
        assert_bad_config(folder, {
            "TRIAL_MODE": "1",
            "TRIAL_BIND_HOST": "0.0.0.0",
            "TRIAL_LAN_ORIGIN": f"http://8.8.8.8:{port}",
        }, port)
        assert_bad_config(folder, {
            "TRIAL_MODE": "1",
            "TRIAL_BIND_HOST": "0.0.0.0",
            "TRIAL_LAN_ORIGIN": f"http://192.168.50.23:{port + 1}",
        }, port, run_server=True)


if __name__ == "__main__":
    run()
    print("✓ LAN 匿名试用：会话、CSRF、Host/Origin 与配置防护全部正确")

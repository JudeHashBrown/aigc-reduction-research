"""HTTP integration tests for account-mode authentication."""
from __future__ import annotations

import http.cookiejar
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
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


PASSWORD = "Correct horse battery 1"
NEW_PASSWORD = "A newly reset password stays private 2"
COOKIE_NAME = "rightthesis_session"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ConsoleReader:
    def __init__(self, proc: subprocess.Popen):
        self.proc = proc
        self.buffer = ""
        os.set_blocking(proc.stdout.fileno(), False)

    def code_for(self, email: str, timeout: float = 5) -> str:
        pattern = re.compile(re.escape(email) + r" 验证码: ([0-9]{6})")
        deadline = time.time() + timeout
        while time.time() < deadline:
            match = pattern.search(self.buffer)
            if match:
                self.buffer = self.buffer[match.end():]
                return match.group(1)
            try:
                chunk = os.read(self.proc.stdout.fileno(), 4096)
            except BlockingIOError:
                chunk = b""
            if chunk:
                self.buffer += chunk.decode("utf-8", "replace")
                continue
            if self.proc.poll() is not None:
                raise AssertionError("account server exited before delivering email code")
            time.sleep(0.02)
        raise AssertionError(f"verification code for {email} was not delivered")


def cookie_value(jar: http.cookiejar.CookieJar, name: str = COOKIE_NAME) -> str:
    values = [cookie.value for cookie in jar if cookie.name == name]
    assert len(values) == 1, f"expected one {name} cookie, got {values}"
    return values[0]


def new_session(opener, base: str) -> dict:
    code, payload, _ = request(opener, base, "/api/session")
    assert code == 200
    assert payload["auth_mode"] == "accounts"
    assert payload["trial_mode"] is False
    assert payload["authenticated"] is False
    assert payload["user"] is None
    assert payload["csrf_token"]
    return payload


def auth_headers(base: str, csrf: str) -> dict[str, str]:
    return {"Origin": base, "X-CSRF-Token": csrf}


def redirect(opener, url: str):
    req = urllib.request.Request(url)
    try:
        opener.open(req, timeout=12)
    except urllib.error.HTTPError as exc:
        assert exc.code in {302, 303}
        return exc.code, exc.headers
    raise AssertionError("expected redirect")


def raw_cookie_session(base: str, token: str) -> tuple[dict, object]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    code, payload, headers = request(
        opener, base, "/api/session", headers={"Cookie": f"{COOKIE_NAME}={token}"},
    )
    assert code == 200
    return payload, headers


def run():
    with tempfile.TemporaryDirectory() as folder_name:
        folder = Path(folder_name)
        database = folder / "accounts.sqlite3"
        port = free_port()
        base = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "AUTH_MODE": "accounts",
            "TRIAL_MODE": "0",
            "TRIAL_BIND_HOST": "127.0.0.1",
            "PUBLIC_ORIGIN": base,
            "GOOGLE_OAUTH_REDIRECT_URI": base + "/api/auth/google/callback",
            "AUTH_SESSION_SECRET": "account-http-test-secret-with-more-than-32-bytes",
            "AUTH_EMAIL_DELIVERY": "console",
            "GOOGLE_OAUTH_CLIENT_ID": "test-client.apps.googleusercontent.com",
            "GOOGLE_OAUTH_CLIENT_SECRET": "test-google-client-secret",
            "BILLING_DB": str(database),
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
        health, _ = opener_with_cookies()
        browser, jar = opener_with_cookies()
        try:
            wait_until_ready(health, base, proc)
            console = ConsoleReader(proc)
            session = new_session(browser, base)
            assert session["providers"] == {
                "email_password": True,
                "google": True,
            }
            first_cookie = cookie_value(jar)

            # A pre-auth browser may inspect prices, but cannot enter any
            # account billing flow or create a Checkout Session.
            checkout_body = {
                "product_id": "student_month",
                "idempotency_key": "guest_checkout_must_be_denied_001",
            }
            code, denied, _ = request(
                browser, base, "/api/billing/checkout", checkout_body,
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 401 and denied["code"] == "authentication_required"
            for billing_path in ("/api/billing/summary", "/api/billing/orders"):
                code, denied, _ = request(browser, base, billing_path)
                assert code == 401 and denied["code"] == "authentication_required"

            # Every account-mode POST requires both exact Origin and CSRF.
            register_body = {
                "email": "http-user@example.com",
                "password": PASSWORD,
                "display_name": "HTTP Author",
            }
            code, _, _ = request(browser, base, "/api/auth/register", register_body)
            assert code == 403
            code, _, _ = request(
                browser, base, "/api/auth/register", register_body,
                {"Origin": "https://evil.example", "X-CSRF-Token": session["csrf_token"]},
            )
            assert code == 403
            code, _, _ = request(
                browser, base, "/api/auth/register", register_body,
                auth_headers(base, "wrong-csrf"),
            )
            assert code == 403

            weak = {**register_body, "password": "short"}
            code, weak_response, _ = request(
                browser, base, "/api/auth/register", weak,
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 400 and weak_response["code"] == "password_policy"

            code, registration, _ = request(
                browser, base, "/api/auth/register", register_body,
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 202
            assert set(registration) == {
                "ok", "message", "challenge_id", "expires_in", "resend_after",
            }
            serialized = json.dumps(registration)
            assert PASSWORD not in serialized and "password_hash" not in serialized
            registration_code = console.code_for("http-user@example.com")

            # The verification screen can replace the code after the shared
            # 60-second cooldown without asking the password to be stored in
            # browser storage or submitted again.
            conn = sqlite3.connect(database)
            try:
                conn.execute(
                    "UPDATE auth_email_challenges SET created_at=created_at-61 "
                    "WHERE id=?", (registration["challenge_id"],),
                )
                conn.commit()
            finally:
                conn.close()
            code, resent, _ = request(
                browser, base, "/api/auth/register/resend",
                {"challenge_id": registration["challenge_id"]},
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 202 and resent["challenge_id"] != registration["challenge_id"]
            resent_code = console.code_for("http-user@example.com")

            code, old_code_result, _ = request(
                browser, base, "/api/auth/register/verify",
                {"challenge_id": registration["challenge_id"], "code": registration_code},
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 400 and old_code_result["code"] == "invalid_or_expired_code"

            # Credentials cannot be used until the mailbox challenge succeeds.
            code, unverified, _ = request(
                browser, base, "/api/auth/login",
                {"email": "http-user@example.com", "password": PASSWORD},
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 401 and unverified["code"] == "invalid_credentials"

            code, verified, verify_headers = request(
                browser, base, "/api/auth/register/verify",
                {"challenge_id": resent["challenge_id"], "code": resent_code},
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 200 and verified["authenticated"] is True
            assert verified["user"]["email"] == "http-user@example.com"
            assert verified["user"]["email_verified"] is True
            assert verified["csrf_token"] != session["csrf_token"]
            assert PASSWORD not in json.dumps(verified)
            authenticated_cookie = cookie_value(jar)
            assert authenticated_cookie != first_cookie
            set_cookie = verify_headers.get("Set-Cookie", "")
            assert "HttpOnly" in set_cookie and "SameSite=Lax" in set_cookie

            stale, stale_headers = raw_cookie_session(base, first_cookie)
            assert stale["authenticated"] is False
            assert stale["csrf_token"] != session["csrf_token"]
            assert "Set-Cookie" in stale_headers

            code, _, _ = request(
                browser, base, "/api/auth/logout", {},
                auth_headers(base, session["csrf_token"]),
            )
            assert code == 403, "pre-login CSRF must die with the rotated session"

            # Create a second authenticated device before resetting the password.
            second_browser, second_jar = opener_with_cookies()
            second_pre = new_session(second_browser, base)
            code, second_login, _ = request(
                second_browser, base, "/api/auth/login",
                {"email": "http-user@example.com", "password": PASSWORD},
                auth_headers(base, second_pre["csrf_token"]),
            )
            assert code == 200 and second_login["authenticated"] is True
            second_cookie = cookie_value(second_jar)

            # Move the completed registration outside the delivery cooldown;
            # this changes only test fixture time, not authentication state.
            conn = sqlite3.connect(database)
            try:
                conn.execute(
                    "UPDATE auth_email_challenges SET created_at=created_at-61 "
                    "WHERE email='http-user@example.com'"
                )
                conn.commit()
            finally:
                conn.close()

            reset_browser, reset_jar = opener_with_cookies()
            reset_pre = new_session(reset_browser, base)
            code, known_forgot, _ = request(
                reset_browser, base, "/api/auth/password/forgot",
                {"email": "http-user@example.com"},
                auth_headers(base, reset_pre["csrf_token"]),
            )
            assert code == 202
            reset_code = console.code_for("http-user@example.com")

            unknown_browser, _ = opener_with_cookies()
            unknown_pre = new_session(unknown_browser, base)
            code, unknown_forgot, _ = request(
                unknown_browser, base, "/api/auth/password/forgot",
                {"email": "unknown@example.com"},
                auth_headers(base, unknown_pre["csrf_token"]),
            )
            assert code == 202
            assert set(known_forgot) == set(unknown_forgot)
            assert known_forgot["message"] == unknown_forgot["message"]
            assert known_forgot["expires_in"] == unknown_forgot["expires_in"]
            assert known_forgot["resend_after"] == unknown_forgot["resend_after"]
            assert "delivery_required" not in known_forgot

            code, reset_result, _ = request(
                reset_browser, base, "/api/auth/password/reset",
                {
                    "challenge_id": known_forgot["challenge_id"],
                    "code": reset_code,
                    "new_password": NEW_PASSWORD,
                },
                auth_headers(base, reset_pre["csrf_token"]),
            )
            assert code == 200 and reset_result["authenticated"] is True
            assert reset_result["csrf_token"] != reset_pre["csrf_token"]

            # Reset revokes every previously authenticated browser session.
            stale_first, _ = raw_cookie_session(base, authenticated_cookie)
            stale_second, _ = raw_cookie_session(base, second_cookie)
            assert stale_first["authenticated"] is False
            assert stale_second["authenticated"] is False

            old_password_browser, _ = opener_with_cookies()
            old_password_pre = new_session(old_password_browser, base)
            code, old_password, _ = request(
                old_password_browser, base, "/api/auth/login",
                {"email": "http-user@example.com", "password": PASSWORD},
                auth_headers(base, old_password_pre["csrf_token"]),
            )
            assert code == 401 and old_password["code"] == "invalid_credentials"

            new_password_browser, _ = opener_with_cookies()
            new_password_pre = new_session(new_password_browser, base)
            code, relogged, _ = request(
                new_password_browser, base, "/api/auth/login",
                {"email": "http-user@example.com", "password": NEW_PASSWORD},
                auth_headers(base, new_password_pre["csrf_token"]),
            )
            assert code == 200 and relogged["authenticated"] is True

            # Google start exposes state, nonce and the S256 challenge, never
            # the verifier or client secret.  Redirect following is disabled.
            google_browser, google_jar = opener_with_cookies()
            new_session(google_browser, base)
            no_redirect = urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPCookieProcessor(google_jar),
                NoRedirect(),
            )
            status, headers = redirect(
                no_redirect, base + "/api/auth/google/start?return_to=%2Fapp",
            )
            assert status == 302
            location = headers["Location"]
            parsed = urllib.parse.urlparse(location)
            query = urllib.parse.parse_qs(parsed.query)
            assert parsed.netloc == "accounts.google.com"
            assert query["code_challenge_method"] == ["S256"]
            assert len(query["state"][0]) >= 32
            assert len(query["nonce"][0]) >= 32
            assert len(query["code_challenge"][0]) >= 43
            assert "code_verifier" not in query
            assert "test-google-client-secret" not in location
        finally:
            stop_server(proc)


if __name__ == "__main__":
    run()
    print("✓ 账号 HTTP：注册验证、登录、防枚举重置、CSRF 与 Google PKCE 全部正确")

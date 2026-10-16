"""Security tests for email/password and Google account authentication."""
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import hmac
import io
import json
import os
import smtplib
import sqlite3
import ssl
import sys
import tempfile
import threading
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

from auth import (  # noqa: E402
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    ARGON2_TIME_COST,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    AuthError,
    AuthStore,
    EmailDelivery,
    GoogleOAuthClient,
)


SECRET = b"rightthesis-auth-test-secret-is-at-least-32-bytes"
PASSWORD = "Correct horse battery 1"
NEW_PASSWORD = "New password keeps every session safe 2"


class Clock:
    def __init__(self, value: float = 1_700_000_000):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += seconds


def expect_auth_error(fn, *, status: int | None = None,
                      codes: set[str] | None = None) -> AuthError:
    try:
        fn()
    except AuthError as exc:
        if status is not None:
            assert exc.status == status, f"expected HTTP {status}, got {exc.status}: {exc}"
        if codes is not None:
            assert exc.code in codes, f"unexpected auth error code: {exc.code}"
        return exc
    raise AssertionError("expected AuthError")


def make_store(folder: Path, clock: Clock) -> tuple[AuthStore, Path]:
    path = folder / "auth.sqlite3"
    return AuthStore(path, SECRET, now=clock), path


def select_one(path: Path, sql: str, params=()) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(sql, params).fetchone()
        assert row is not None
        return dict(row)
    finally:
        conn.close()


def challenge_row(path: Path, challenge_id: str) -> dict:
    return select_one(
        path, "SELECT * FROM auth_email_challenges WHERE id=?", (challenge_id,),
    )


def password_hash_for(path: Path, email: str) -> str:
    row = select_one(
        path,
        """SELECT c.password_hash FROM auth_password_credentials c
           JOIN auth_verified_emails e ON e.account_id=c.account_id
           WHERE e.email=?""",
        (email,),
    )
    return row["password_hash"]


def assert_argon2id(value: str) -> None:
    assert value.startswith("$argon2id$")
    assert f"m={ARGON2_MEMORY_COST},t={ARGON2_TIME_COST},p={ARGON2_PARALLELISM}" in value


def register(store: AuthStore, email: str, password: str = PASSWORD,
             display_name: str = "Author") -> tuple[dict, dict, dict]:
    pre_auth = store.create_pre_auth()
    challenge = store.begin_registration(
        pre_auth["token"], email, password, display_name,
    )
    logged_in = store.verify_registration(
        pre_auth["token"], challenge["challenge_id"], challenge["code"],
    )
    return pre_auth, challenge, logged_in


def test_password_policy_and_argon2id_storage():
    with tempfile.TemporaryDirectory() as name:
        clock = Clock()
        store, path = make_store(Path(name), clock)

        for invalid_email in (
            "route:victim@example.com",
            "route,victim@example.com",
            "Victim <victim@example.com>",
            "group:one@example.com;",
            ".leading@example.com",
            "double..dot@example.com",
        ):
            invalid_session = store.create_pre_auth()
            expect_auth_error(
                lambda value=invalid_email, session=invalid_session: store.begin_registration(
                    session["token"], value, PASSWORD,
                ),
                codes={"invalid_email"},
            )

        for bad in ("Aa123", "Aa1" + "x" * (PASSWORD_MAX_LENGTH - 2),
                    "abc123", "ABC123", "Abcdef", "论" * PASSWORD_MIN_LENGTH):
            session = store.create_pre_auth()
            expect_auth_error(
                lambda bad=bad, session=session: store.begin_registration(
                    session["token"], "policy@example.com", bad,
                ),
                codes={"password_policy"},
            )

        # Unicode remains accepted alongside the three required ASCII classes.
        unicode_password = "Aa1论文稿"
        pre_auth = store.create_pre_auth()
        challenge = store.begin_registration(
            pre_auth["token"], "  Student@Example.COM ", unicode_password, "学 生",
        )
        assert challenge["email"] == "student@example.com"
        row = challenge_row(path, challenge["challenge_id"])
        assert row["purpose"] == "register"
        payload = json.loads(row["payload_json"])
        pending_hash = payload["password_hash"]
        assert_argon2id(pending_hash)
        assert pending_hash != unicode_password
        assert unicode_password not in row["payload_json"]

        session_hash = hashlib.sha256(pre_auth["token"].encode()).hexdigest()
        raw = "\0".join((
            "email-challenge-v2", challenge["challenge_id"], session_hash,
            challenge["email"], "register", challenge["code"],
        ))
        expected = hmac.new(SECRET, raw.encode(), hashlib.sha256).hexdigest()
        assert row["code_hmac"] == expected
        assert row["code_hmac"] != challenge["code"]

        store.verify_registration(
            pre_auth["token"], challenge["challenge_id"], challenge["code"],
        )
        persisted_hash = password_hash_for(path, "student@example.com")
        assert_argon2id(persisted_hash)
        assert persisted_hash == pending_hash

        conn = sqlite3.connect(path)
        try:
            values = [
                str(value)
                for table in ("auth_email_challenges", "auth_password_credentials")
                for row_value in conn.execute(f"SELECT * FROM {table}").fetchall()
                for value in row_value
            ]
        finally:
            conn.close()
        assert unicode_password not in values

        # A policy change must not lock out accounts with older passwords.
        legacy_password = "correct horse battery staple"
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "UPDATE auth_password_credentials SET password_hash=?",
                (store.password_hasher.hash(legacy_password),),
            )
            conn.commit()
        finally:
            conn.close()
        legacy_session = store.create_pre_auth()
        assert store.login_password(
            legacy_session["token"], "student@example.com", legacy_password,
        )["authenticated"]


def test_registration_requires_verification_and_rotates_session():
    with tempfile.TemporaryDirectory() as name:
        clock = Clock()
        store, _ = make_store(Path(name), clock)
        owner = store.create_pre_auth()
        challenge = store.begin_registration(
            owner["token"], "author@example.com", PASSWORD, "Author",
        )

        before_verification = store.create_pre_auth()
        error = expect_auth_error(
            lambda: store.login_password(
                before_verification["token"], "author@example.com", PASSWORD,
            ),
            status=401, codes={"invalid_credentials"},
        )
        assert str(error) == "邮箱或密码错误。"

        other = store.create_pre_auth()
        expect_auth_error(
            lambda: store.verify_registration(
                other["token"], challenge["challenge_id"], challenge["code"],
            ),
            codes={"invalid_or_expired_code"},
        )

        logged_in = store.verify_registration(
            owner["token"], challenge["challenge_id"], challenge["code"],
        )
        assert logged_in["authenticated"] is True
        assert logged_in["csrf_token"] != owner["csrf_token"]
        assert store.authenticate_session(owner["token"]) is None
        assert logged_in["user"]["email_verified"] is True
        assert logged_in["user"]["email"] == "author@example.com"
        assert "password" not in json.dumps(logged_in).lower()

        expect_auth_error(
            lambda: store.verify_registration(
                owner["token"], challenge["challenge_id"], challenge["code"],
            ),
            codes={"invalid_or_expired_code"},
        )

        login_pre_auth = store.create_pre_auth()
        second_login = store.login_password(
            login_pre_auth["token"], "AUTHOR@EXAMPLE.COM", PASSWORD,
        )
        assert second_login["authenticated"] is True
        assert second_login["token"] != login_pre_auth["token"]
        assert second_login["csrf_token"] != login_pre_auth["csrf_token"]
        assert store.authenticate_session(login_pre_auth["token"]) is None

        race_pre_auth = store.create_pre_auth()
        barrier = threading.Barrier(2)

        def concurrent_login():
            barrier.wait()
            try:
                return store.login_password(
                    race_pre_auth["token"], "author@example.com", PASSWORD,
                )
            except AuthError as exc:
                return exc

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: concurrent_login(), range(2)))
        assert sum(isinstance(item, dict) for item in outcomes) == 1
        replay_errors = [item for item in outcomes if isinstance(item, AuthError)]
        assert len(replay_errors) == 1
        assert replay_errors[0].code == "preauth_session_required"

        known = store.create_pre_auth()
        known_error = expect_auth_error(
            lambda: store.login_password(
                known["token"], "author@example.com", "definitely the wrong password",
            ),
            status=401, codes={"invalid_credentials"},
        )
        unknown = store.create_pre_auth()
        unknown_error = expect_auth_error(
            lambda: store.login_password(
                unknown["token"], "unknown@example.com", "definitely the wrong password",
            ),
            status=401, codes={"invalid_credentials"},
        )
        assert str(known_error) == str(unknown_error)


def test_registration_code_expiry_attempts_cooldown_and_purpose_binding():
    with tempfile.TemporaryDirectory() as name:
        clock = Clock()
        store, _ = make_store(Path(name), clock)

        cooldown_session = store.create_pre_auth()
        original = store.begin_registration(
            cooldown_session["token"], "cooldown@example.com", PASSWORD,
        )
        cooldown = expect_auth_error(
            lambda: store.resend_registration(
                cooldown_session["token"], original["challenge_id"],
            ),
            status=429, codes={"email_code_cooldown"},
        )
        assert cooldown.retry_after and cooldown.retry_after > 0
        clock.advance(60)
        replacement = store.resend_registration(
            cooldown_session["token"], original["challenge_id"],
        )
        assert replacement["challenge_id"] != original["challenge_id"]
        assert challenge_row(store.path, original["challenge_id"])["consumed_at"] is not None
        expect_auth_error(
            lambda: store.verify_registration(
                cooldown_session["token"], original["challenge_id"], original["code"],
            ),
            codes={"invalid_or_expired_code"},
        )
        resent_login = store.verify_registration(
            cooldown_session["token"], replacement["challenge_id"], replacement["code"],
        )
        assert resent_login["authenticated"] is True

        expiry_session = store.create_pre_auth()
        expiring = store.begin_registration(
            expiry_session["token"], "expiry@example.com", PASSWORD,
        )
        clock.advance(expiring["expires_in"])
        expect_auth_error(
            lambda: store.verify_registration(
                expiry_session["token"], expiring["challenge_id"], expiring["code"],
            ),
            codes={"invalid_or_expired_code"},
        )

        limited_session = store.create_pre_auth()
        limited = store.begin_registration(
            limited_session["token"], "attempts@example.com", PASSWORD,
        )
        wrong_code = "000000" if limited["code"] != "000000" else "000001"
        for _ in range(5):
            expect_auth_error(
                lambda: store.verify_registration(
                    limited_session["token"], limited["challenge_id"], wrong_code,
                ),
                codes={"invalid_or_expired_code"},
            )
        expect_auth_error(
            lambda: store.verify_registration(
                limited_session["token"], limited["challenge_id"], limited["code"],
            ),
            codes={"invalid_or_expired_code"},
        )

        purpose_session = store.create_pre_auth()
        purpose = store.begin_registration(
            purpose_session["token"], "purpose@example.com", PASSWORD,
        )
        expect_auth_error(
            lambda: store.reset_password(
                purpose_session["token"], purpose["challenge_id"],
                purpose["code"], NEW_PASSWORD,
            ),
            codes={"invalid_or_expired_code"},
        )
        registered = store.verify_registration(
            purpose_session["token"], purpose["challenge_id"], purpose["code"],
        )
        assert registered["authenticated"] is True


def test_password_reset_is_non_enumerating_single_use_and_revokes_sessions():
    with tempfile.TemporaryDirectory() as name:
        clock = Clock()
        store, path = make_store(Path(name), clock)
        _registration_pre, _challenge, first_session = register(
            store, "reset@example.com",
        )
        second_pre = store.create_pre_auth()
        second_session = store.login_password(
            second_pre["token"], "reset@example.com", PASSWORD,
        )
        old_hash = password_hash_for(path, "reset@example.com")

        # Registration and password-reset delivery share a mailbox cooldown.
        clock.advance(60)
        reset_pre = store.create_pre_auth()
        known = store.begin_password_reset(reset_pre["token"], "reset@example.com")
        unknown_pre = store.create_pre_auth()
        unknown = store.begin_password_reset(
            unknown_pre["token"], "not-registered@example.com",
        )
        public_keys = {"challenge_id", "expires_in", "resend_after"}
        assert public_keys <= known.keys() and public_keys <= unknown.keys()
        assert known["delivery_required"] is True
        assert unknown["delivery_required"] is False
        assert known["expires_in"] == unknown["expires_in"]
        assert known["resend_after"] == unknown["resend_after"]

        expect_auth_error(
            lambda: store.reset_password(
                unknown_pre["token"], known["challenge_id"],
                known["code"], NEW_PASSWORD,
            ),
            codes={"invalid_or_expired_code"},
        )

        reset_session = store.reset_password(
            reset_pre["token"], known["challenge_id"], known["code"], NEW_PASSWORD,
        )
        assert reset_session["authenticated"] is True
        new_hash = password_hash_for(path, "reset@example.com")
        assert_argon2id(new_hash)
        assert new_hash != old_hash
        assert store.authenticate_session(first_session["token"]) is None
        assert store.authenticate_session(second_session["token"]) is None

        expect_auth_error(
            lambda: store.reset_password(
                reset_pre["token"], known["challenge_id"], known["code"], NEW_PASSWORD,
            ),
            codes={"invalid_or_expired_code"},
        )
        expect_auth_error(
            lambda: store.reset_password(
                unknown_pre["token"], unknown["challenge_id"],
                unknown["code"], NEW_PASSWORD,
            ),
            codes={"invalid_or_expired_code"},
        )

        old_password_pre = store.create_pre_auth()
        expect_auth_error(
            lambda: store.login_password(
                old_password_pre["token"], "reset@example.com", PASSWORD,
            ),
            status=401, codes={"invalid_credentials"},
        )
        new_password_pre = store.create_pre_auth()
        relogged = store.login_password(
            new_password_pre["token"], "reset@example.com", NEW_PASSWORD,
        )
        assert relogged["authenticated"] is True


def test_oauth_state_pkce_nonce_and_single_consumption():
    with tempfile.TemporaryDirectory() as name:
        clock = Clock()
        store, _ = make_store(Path(name), clock)
        owner = store.create_pre_auth()
        other = store.create_pre_auth()
        flow = store.create_oauth_flow(
            owner["token"], "/app", "https://rightthesis.example/api/auth/google/callback",
        )

        assert len(flow["state"]) >= 32
        assert len(flow["nonce"]) >= 32
        assert 43 <= len(flow["code_verifier"]) <= 128
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(flow["code_verifier"].encode("ascii")).digest(),
        ).rstrip(b"=").decode("ascii")
        assert flow["code_challenge"] == expected

        expect_auth_error(
            lambda: store.consume_oauth_flow(other["token"], flow["state"]),
            codes={"invalid_oauth_state"},
        )
        consumed = store.consume_oauth_flow(owner["token"], flow["state"])
        assert consumed["nonce"] == flow["nonce"]
        assert consumed["code_verifier"] == flow["code_verifier"]
        assert consumed["return_to"] == "/app"
        expect_auth_error(
            lambda: store.consume_oauth_flow(owner["token"], flow["state"]),
            codes={"invalid_oauth_state"},
        )

        sanitized = store.create_oauth_flow(
            owner["token"], "https://evil.example/steal",
            "https://rightthesis.example/api/auth/google/callback",
        )
        assert sanitized["return_to"] == "/app"


def test_google_token_exchange_reports_actionable_errors():
    client = GoogleOAuthClient("test-client-id", "test-client-secret")
    flow = {
        "redirect_uri": "https://rightthesis.example/api/auth/google/callback",
        "code_verifier": "a" * 64,
        "nonce": "test-nonce",
    }
    invalid_client = HTTPError(
        client.TOKEN_ENDPOINT, 401, "Unauthorized", {},
        io.BytesIO(b'{"error":"invalid_client"}'),
    )
    with patch("auth.urlopen", side_effect=invalid_client) as token_request:
        expect_auth_error(
            lambda: client.exchange_and_verify("test-code", flow),
            codes={"google_client_invalid"},
        )
        tls_context = token_request.call_args.kwargs["context"]
        assert tls_context.verify_mode == ssl.CERT_REQUIRED
        assert tls_context.check_hostname
        assert tls_context.cert_store_stats()["x509"] > 0
    with patch("auth.urlopen", side_effect=URLError("proxy unavailable")):
        expect_auth_error(
            lambda: client.exchange_and_verify("test-code", flow),
            status=503, codes={"google_network_error"},
        )


def test_smtp_delivery_requires_complete_config_and_verified_tls():
    incomplete = EmailDelivery(
        mode="smtp", sender="no-reply@example.com",
        smtp_host="smtp.example.com", smtp_port=465,
        smtp_username="no-reply@example.com", smtp_ssl=True,
        smtp_starttls=False,
    )
    assert not incomplete.configured
    expect_auth_error(
        lambda: incomplete.send_code("reader@example.com", "123456",
                                     wait_for_delivery=True),
        status=503, codes={"email_login_unavailable"},
    )

    delivery = EmailDelivery(
        mode="smtp", sender="no-reply@example.com",
        smtp_host="smtp.example.com", smtp_port=465,
        smtp_username="no-reply@example.com", smtp_password="test-app-password",
        smtp_ssl=True, smtp_starttls=False,
    )
    assert delivery.configured
    smtp_connection = MagicMock()
    smtp_connection.__enter__.return_value = smtp_connection
    with patch("auth.smtplib.SMTP_SSL", return_value=smtp_connection) as smtp:
        delivery.send_code("reader@example.com", "123456",
                           wait_for_delivery=True)
    tls_context = smtp.call_args.kwargs["context"]
    assert tls_context.verify_mode == ssl.CERT_REQUIRED
    assert tls_context.check_hostname
    assert tls_context.cert_store_stats()["x509"] > 0
    smtp_connection.login.assert_called_once_with(
        "no-reply@example.com", "test-app-password",
    )
    message = smtp_connection.send_message.call_args.args[0]
    assert message["To"] == "reader@example.com"
    assert "123456" in message.get_content()

    with patch("auth.smtplib.SMTP_SSL", side_effect=smtplib.SMTPAuthenticationError(
            535, b"authentication failed")):
        expect_auth_error(
            lambda: delivery.send_code("reader@example.com", "654321",
                                       wait_for_delivery=True),
            status=503, codes={"email_delivery_failed"},
        )

    with patch.dict(os.environ, {
        "AUTH_EMAIL_DELIVERY": "smtp",
        "AUTH_EMAIL_FROM": "no-reply@example.com",
        "AUTH_SMTP_HOST": "smtp.example.com",
        "AUTH_SMTP_PORT": "465",
        "AUTH_SMTP_USERNAME": "no-reply@example.com",
        "AUTH_SMTP_PASSWORD": "test-app-password",
        "AUTH_SMTP_SSL": "1",
        "AUTH_SMTP_STARTTLS": "0",
        "AUTH_SMTP_PROXY_URL": "http://127.0.0.1:7890",
    }, clear=True):
        proxied = EmailDelivery.from_env()
        assert proxied.configured
        assert proxied.smtp_proxy_url == "http://127.0.0.1:7890"
        os.environ["AUTH_SMTP_SSL"] = "0"
        assert not EmailDelivery.from_env().configured
        os.environ["AUTH_SMTP_PROXY_URL"] = "http://user:secret@127.0.0.1:7890"
        try:
            EmailDelivery.from_env()
        except RuntimeError:
            pass
        else:
            raise AssertionError("proxy URL with credentials must be rejected")


TESTS = [
    test_password_policy_and_argon2id_storage,
    test_registration_requires_verification_and_rotates_session,
    test_registration_code_expiry_attempts_cooldown_and_purpose_binding,
    test_password_reset_is_non_enumerating_single_use_and_revokes_sessions,
    test_oauth_state_pkce_nonce_and_single_consumption,
    test_google_token_exchange_reports_actionable_errors,
    test_smtp_delivery_requires_complete_config_and_verified_tls,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"✓ 账号认证 {len(TESTS)} 组：Argon2id、邮箱验证、重置撤销与 OAuth 防重放全部正确")

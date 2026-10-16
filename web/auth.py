"""Production-shaped account sessions for RightThesis.

The local and anonymous-trial modes intentionally remain independent.  When
``AUTH_MODE=accounts`` this module provides:

* opaque, revocable browser sessions backed by SQLite;
* email/password accounts with verified registration and password reset;
* one-time Google OAuth transactions with state, nonce and PKCE; and
* stable provider identities linked to the existing billing ``accounts`` row.

No OAuth token or plaintext email code is persisted.  The module only uses the
standard library except for Google ID-token verification, which is imported
lazily by :class:`GoogleOAuthClient` when Google login is configured.
"""
from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import queue
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as UrlRequest, urlopen

import certifi
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type


AUTH_COOKIE_NAME = "rightthesis_session"
EMAIL_CODE_SECONDS = 10 * 60
EMAIL_CODE_ATTEMPTS = 5
EMAIL_RESEND_SECONDS = 60
OAUTH_FLOW_SECONDS = 10 * 60
PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_LENGTH = 128
ARGON2_MEMORY_COST = 19 * 1024
ARGON2_TIME_COST = 2
ARGON2_PARALLELISM = 1


class AuthError(RuntimeError):
    """An expected authentication failure safe to map to an HTTP response."""

    def __init__(self, message: str, status: int = 400,
                 code: str = "auth_error", retry_after: Optional[int] = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = retry_after


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _b64url(raw: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def normalize_email(value: str) -> str:
    """Return a conservative canonical mailbox without provider-specific rules."""
    if not isinstance(value, str):
        raise AuthError("请输入有效邮箱地址。", code="invalid_email")
    value = unicodedata.normalize("NFKC", value).strip()
    if len(value) > 254 or value.count("@") != 1:
        raise AuthError("请输入有效邮箱地址。", code="invalid_email")
    local, domain = value.rsplit("@", 1)
    if not local or len(local) > 64 or not domain:
        raise AuthError("请输入有效邮箱地址。", code="invalid_email")
    # Accept one conservative SMTP dot-atom only.  Display names, group
    # syntax, comments and separators must never reach ``EmailMessage['To']``:
    # parsers can reinterpret values such as ``route:victim@example.com`` and
    # defeat mailbox-keyed rate limits.
    atom = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    if (any(char.isspace() or ord(char) < 32 for char in local)
            or not re.fullmatch(rf"{atom}(?:\.{atom})*", local)):
        raise AuthError("请输入有效邮箱地址。", code="invalid_email")
    try:
        domain = domain.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise AuthError("请输入有效邮箱地址。", code="invalid_email") from exc
    if (not domain or "." not in domain
            or not re.fullmatch(r"[a-z0-9.-]+", domain)
            or any(not part or len(part) > 63 or part[0] == "-" or part[-1] == "-"
                   for part in domain.split("."))):
        raise AuthError("请输入有效邮箱地址。", code="invalid_email")
    # Case-folding the local part is the interoperable choice for login lookup.
    # Deliberately do not remove dots or plus-tags: those are provider-specific.
    return f"{local.casefold()}@{domain}"


def validate_password(value: str) -> str:
    """Validate without trimming, normalizing or silently rewriting a password."""
    policy_message = (
        f"密码需为 {PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} 个字符，"
        "且包含大写字母、小写字母和数字。"
    )
    if not isinstance(value, str):
        raise AuthError(policy_message, code="password_policy")
    length = len(value)
    if (length < PASSWORD_MIN_LENGTH or length > PASSWORD_MAX_LENGTH
            or not re.search(r"[A-Z]", value)
            or not re.search(r"[a-z]", value)
            or not re.search(r"[0-9]", value)):
        raise AuthError(policy_message, code="password_policy")
    return value


def normalize_display_name(value: str | None) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AuthError("显示名称格式无效。", code="invalid_display_name")
    value = unicodedata.normalize("NFKC", value).strip()
    if len(value) > 120 or any(ord(char) < 32 for char in value):
        raise AuthError("显示名称格式无效。", code="invalid_display_name")
    return value


def safe_return_to(value: str | None) -> str:
    """Allow one internal SPA path and reject scheme-relative/open redirects."""
    if not isinstance(value, str) or not value:
        return "/app"
    if (not value.startswith("/") or value.startswith("//")
            or "\\" in value or "\r" in value or "\n" in value):
        return "/app"
    # RightThesis uses hash routing; query/fragment data is not needed here.
    value = value.split("?", 1)[0].split("#", 1)[0]
    if not re.fullmatch(r"/[A-Za-z0-9_./-]*", value):
        return "/app"
    return value


class AuthStore:
    def __init__(self, path: Path | str, secret: bytes,
                 session_seconds: int = 7 * 24 * 60 * 60,
                 now: Optional[Callable[[], float]] = None):
        if len(secret) < 32:
            raise ValueError("auth secret must contain at least 32 bytes")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.secret = secret
        self.session_seconds = max(300, int(session_seconds))
        self._now = now or time.time
        self.password_hasher = PasswordHasher(
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST,
            parallelism=ARGON2_PARALLELISM,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        # Always verify one Argon2id hash on login, including unknown emails,
        # so the common timing path does not disclose account existence.
        self._dummy_password_hash = self.password_hasher.hash(
            secrets.token_urlsafe(24),
        )
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self):
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_profiles (
                    account_id TEXT PRIMARY KEY REFERENCES accounts(id),
                    primary_email TEXT,
                    display_name TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_verified_emails (
                    email TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    verified_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_identities (
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    verified_email TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY(provider, subject)
                );
                CREATE INDEX IF NOT EXISTS idx_auth_identities_account
                    ON auth_identities(account_id);
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL REFERENCES accounts(id),
                    authenticated INTEGER NOT NULL CHECK(authenticated IN (0,1)),
                    csrf_token TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_account
                    ON auth_sessions(account_id, expires_at);
                CREATE TABLE IF NOT EXISTS auth_email_challenges (
                    id TEXT PRIMARY KEY,
                    session_hash TEXT NOT NULL,
                    email TEXT NOT NULL,
                    purpose TEXT NOT NULL DEFAULT 'legacy_passwordless',
                    code_hmac TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_auth_email_recent
                    ON auth_email_challenges(email, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_auth_email_session
                    ON auth_email_challenges(session_hash, created_at DESC);
                CREATE TABLE IF NOT EXISTS auth_password_credentials (
                    account_id TEXT PRIMARY KEY REFERENCES accounts(id),
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_key TEXT NOT NULL,
                    session_hash TEXT NOT NULL,
                    succeeded INTEGER NOT NULL CHECK(succeeded IN (0,1)),
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_login_email_time
                    ON auth_login_attempts(email_key, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_auth_login_session_time
                    ON auth_login_attempts(session_hash, created_at DESC);
                CREATE TABLE IF NOT EXISTS auth_oauth_flows (
                    state_hash TEXT PRIMARY KEY,
                    session_hash TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    code_verifier TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    return_to TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    consumed_at INTEGER
                );
            """)
            # Additive migration for databases created by the earlier
            # passwordless prototype.  No account, billing or challenge row is
            # rewritten; legacy challenges simply cannot satisfy a password
            # purpose check.
            columns = {row["name"] for row in conn.execute(
                "PRAGMA table_info(auth_email_challenges)",
            ).fetchall()}
            if "purpose" not in columns:
                conn.execute(
                    "ALTER TABLE auth_email_challenges "
                    "ADD COLUMN purpose TEXT NOT NULL DEFAULT 'legacy_passwordless'"
                )
            if "payload_json" not in columns:
                conn.execute(
                    "ALTER TABLE auth_email_challenges "
                    "ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'"
                )
        finally:
            conn.close()

    @staticmethod
    def _insert_account(conn: sqlite3.Connection, account_id: str, now: int):
        conn.execute(
            "INSERT OR IGNORE INTO accounts(id,created_at,updated_at) VALUES(?,?,?)",
            (account_id, now, now),
        )

    def _new_session(self, conn: sqlite3.Connection, account_id: str,
                     authenticated: bool, now: int) -> dict:
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(24)
        expires_at = now + self.session_seconds
        conn.execute(
            """INSERT INTO auth_sessions
               (token_hash,account_id,authenticated,csrf_token,created_at,expires_at)
               VALUES(?,?,?,?,?,?)""",
            (_token_hash(token), account_id, int(authenticated), csrf, now, expires_at),
        )
        return {
            "token": token,
            "csrf_token": csrf,
            "account_id": account_id,
            "authenticated": bool(authenticated),
            "expires_at": expires_at,
        }

    def create_pre_auth(self) -> dict:
        now = int(self._now())
        # Pre-auth sessions share one non-billable placeholder account.  A
        # fresh unauthenticated GET must not leave a permanent account row;
        # first successful identity verification creates the real account.
        account_id = "auth_preauth"
        with self._transaction() as conn:
            self._insert_account(conn, account_id, now)
            session = self._new_session(conn, account_id, False, now)
            self._purge(conn, now)
        session["user"] = None
        return session

    @staticmethod
    def _profile_user(conn: sqlite3.Connection, account_id: str) -> Optional[dict]:
        row = conn.execute(
            "SELECT * FROM auth_profiles WHERE account_id=?", (account_id,),
        ).fetchone()
        if not row:
            return None
        providers = [item["provider"] for item in conn.execute(
            "SELECT provider FROM auth_identities WHERE account_id=? ORDER BY provider",
            (account_id,),
        ).fetchall()]
        display_name = row["display_name"] or row["primary_email"].split("@", 1)[0]
        return {
            "id": account_id,
            "account_id": account_id,
            "email": row["primary_email"],
            "email_verified": True,
            "name": display_name,
            "display_name": display_name,
            "label": display_name,
            "avatar_url": row["avatar_url"] or None,
            "kind": "account",
            "providers": providers,
        }

    def authenticate_session(self, token: Optional[str]) -> Optional[dict]:
        if not isinstance(token, str) or len(token) < 32:
            return None
        now = int(self._now())
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT * FROM auth_sessions
                   WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?""",
                (_token_hash(token), now),
            ).fetchone()
            if not row:
                return None
            authenticated = bool(row["authenticated"])
            user = self._profile_user(conn, row["account_id"]) if authenticated else None
            if authenticated and user is None:
                return None
            return {
                "token": token,
                "token_hash": row["token_hash"],
                "account_id": row["account_id"],
                "authenticated": authenticated,
                "csrf_token": row["csrf_token"],
                "expires_at": int(row["expires_at"]),
                "user": user,
            }
        finally:
            conn.close()

    def revoke_session(self, token: Optional[str]):
        if not isinstance(token, str) or len(token) < 32:
            return
        now = int(self._now())
        with self._transaction() as conn:
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (now, _token_hash(token)),
            )

    @staticmethod
    def _purge(conn: sqlite3.Connection, now: int):
        cutoff = now - 24 * 60 * 60
        conn.execute("DELETE FROM auth_oauth_flows WHERE expires_at<?", (cutoff,))
        conn.execute("DELETE FROM auth_email_challenges WHERE expires_at<?", (cutoff,))
        conn.execute("DELETE FROM auth_sessions WHERE expires_at<?", (cutoff,))
        conn.execute("DELETE FROM auth_login_attempts WHERE created_at<?", (cutoff,))
        # Remove orphaned per-request guest rows left by pre-account builds.
        # Billing tables are included only when they exist, so AuthStore also
        # remains usable in its standalone security tests.
        tables = {row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        ).fetchall()}
        references = [
            ("auth_profiles", "account_id"),
            ("auth_verified_emails", "account_id"),
            ("auth_identities", "account_id"),
            ("auth_password_credentials", "account_id"),
            ("auth_sessions", "account_id"),
            ("orders", "account_id"),
            ("credit_grants", "account_id"),
            ("usage_reservations", "account_id"),
            ("ledger_entries", "account_id"),
        ]
        guards = [
            f"NOT EXISTS (SELECT 1 FROM {table} WHERE {table}.{column}=accounts.id)"
            for table, column in references if table in tables
        ]
        if guards:
            conn.execute(
                "DELETE FROM accounts WHERE substr(id,1,6)='guest_' AND "
                + " AND ".join(guards)
            )

    def _challenge_hmac(self, challenge_id: str, session_hash: str,
                        email: str, purpose: str, code: str) -> str:
        raw = "\0".join(("email-challenge-v2", challenge_id, session_hash,
                          email, purpose, code))
        return hmac.new(self.secret, raw.encode("utf-8"), hashlib.sha256).hexdigest()

    def _email_key(self, email: str) -> str:
        return hmac.new(
            self.secret, ("login-rate-v1\0" + email).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _begin_email_challenge(self, session_token: str, email: str,
                               purpose: str, payload: dict,
                               delivery_required: bool) -> dict:
        session = self.authenticate_session(session_token)
        if not session or session["authenticated"]:
            raise AuthError("请刷新页面后重试。", 401, "preauth_session_required")
        normalized = normalize_email(email)
        now = int(self._now())
        session_hash = session["token_hash"]
        with self._transaction() as conn:
            latest = conn.execute(
                """SELECT created_at FROM auth_email_challenges
                   WHERE (email=? OR session_hash=?)
                   ORDER BY created_at DESC LIMIT 1""",
                (normalized, session_hash),
            ).fetchone()
            if latest and now - int(latest["created_at"]) < EMAIL_RESEND_SECONDS:
                retry = EMAIL_RESEND_SECONDS - (now - int(latest["created_at"]))
                raise AuthError("请稍后再获取验证码。", 429,
                                "email_code_cooldown", retry)
            # Keep a bounded persistent rate limit.  It is deliberately keyed
            # by both normalized mailbox and the untrusted browser flow, never
            # by spoofable X-Forwarded-For.
            email_count = conn.execute(
                "SELECT COUNT(*) AS n FROM auth_email_challenges WHERE email=? AND created_at>?",
                (normalized, now - 3600),
            ).fetchone()["n"]
            session_count = conn.execute(
                "SELECT COUNT(*) AS n FROM auth_email_challenges WHERE session_hash=? AND created_at>?",
                (session_hash, now - 3600),
            ).fetchone()["n"]
            if int(email_count) >= 6 or int(session_count) >= 20:
                raise AuthError("请稍后再试。", 429, "email_rate_limited", 3600)
            conn.execute(
                """UPDATE auth_email_challenges SET consumed_at=?
                   WHERE session_hash=? AND email=? AND purpose=? AND consumed_at IS NULL""",
                (now, session_hash, normalized, purpose),
            )
            challenge_id = "emc_" + secrets.token_urlsafe(18)
            code = f"{secrets.randbelow(1_000_000):06d}"
            expires_at = now + EMAIL_CODE_SECONDS
            conn.execute(
                """INSERT INTO auth_email_challenges
                   (id,session_hash,email,purpose,code_hmac,payload_json,
                    max_attempts,created_at,expires_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (challenge_id, session_hash, normalized, purpose,
                 self._challenge_hmac(
                     challenge_id, session_hash, normalized, purpose, code),
                 json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                 EMAIL_CODE_ATTEMPTS, now, expires_at),
            )
        return {
            "challenge_id": challenge_id,
            "code": code,
            "email": normalized,
            "expires_in": EMAIL_CODE_SECONDS,
            "resend_after": EMAIL_RESEND_SECONDS,
            "purpose": purpose,
            "delivery_required": bool(delivery_required),
        }

    def invalidate_email_challenge(self, challenge_id: str):
        now = int(self._now())
        with self._transaction() as conn:
            conn.execute(
                "UPDATE auth_email_challenges SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
                (now, challenge_id),
            )

    def _verify_email_challenge(self, session_token: str, challenge_id: str,
                                code: str, purpose: str) -> dict:
        session = self.authenticate_session(session_token)
        if not session or session["authenticated"]:
            raise AuthError("验证码无效或已过期。", 400, "invalid_or_expired_code")
        if (not isinstance(challenge_id, str) or not isinstance(code, str)
                or not re.fullmatch(r"[0-9]{6}", code)):
            raise AuthError("验证码无效或已过期。", 400, "invalid_or_expired_code")
        now = int(self._now())
        session_hash = session["token_hash"]
        failed_attempt = False
        verified_identity = None
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM auth_email_challenges WHERE id=?",
                (challenge_id,),
            ).fetchone()
            invalid = (not row or row["session_hash"] != session_hash
                       or row["purpose"] != purpose
                       or row["consumed_at"] is not None
                       or int(row["expires_at"]) <= now
                       or int(row["attempts"]) >= int(row["max_attempts"]))
            if invalid:
                raise AuthError("验证码无效或已过期。", 400,
                                "invalid_or_expired_code")
            expected = self._challenge_hmac(
                challenge_id, session_hash, row["email"], purpose, code,
            )
            if not hmac.compare_digest(row["code_hmac"], expected):
                attempts = int(row["attempts"]) + 1
                consumed = now if attempts >= int(row["max_attempts"]) else None
                conn.execute(
                    "UPDATE auth_email_challenges SET attempts=?, consumed_at=? WHERE id=?",
                    (attempts, consumed, challenge_id),
                )
                failed_attempt = True
            else:
                updated = conn.execute(
                    """UPDATE auth_email_challenges SET consumed_at=?
                       WHERE id=? AND consumed_at IS NULL""",
                    (now, challenge_id),
                )
                if updated.rowcount != 1:
                    raise AuthError("验证码无效或已过期。", 400,
                                    "invalid_or_expired_code")
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except json.JSONDecodeError:
                    payload = {}
                verified_identity = {"email": row["email"], "payload": payload}
        # Raising outside the transaction is intentional: wrong-attempt state
        # must commit, otherwise a brute-forcer receives unlimited guesses.
        if failed_attempt:
            raise AuthError("验证码无效或已过期。", 400,
                            "invalid_or_expired_code")
        return verified_identity

    def begin_registration(self, session_token: str, email: str,
                           password: str, display_name: str = "") -> dict:
        normalized = normalize_email(email)
        password_hash = self.password_hasher.hash(validate_password(password))
        name = normalize_display_name(display_name)
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT c.account_id FROM auth_verified_emails e
                   JOIN auth_password_credentials c ON c.account_id=e.account_id
                   WHERE e.email=?""",
                (normalized,),
            ).fetchone()
        finally:
            conn.close()
        return self._begin_email_challenge(
            session_token, normalized, "register",
            {"password_hash": password_hash, "display_name": name,
             "eligible": row is None},
            delivery_required=True,
        )

    def verify_registration(self, session_token: str, challenge_id: str,
                            code: str) -> dict:
        verified = self._verify_email_challenge(
            session_token, challenge_id, code, "register",
        )
        payload = verified["payload"]
        if not payload.get("eligible") or not isinstance(payload.get("password_hash"), str):
            raise AuthError("无法完成注册，请改用登录或找回密码。", 409,
                            "registration_unavailable")
        logged_in = self.rotate_authenticated(
            session_token,
            provider="email",
            subject=verified["email"],
            email=verified["email"],
            display_name=payload.get("display_name") or verified["email"].split("@", 1)[0],
            avatar_url="",
        )
        now = int(self._now())
        try:
            with self._transaction() as conn:
                existing = conn.execute(
                    "SELECT 1 FROM auth_password_credentials WHERE account_id=?",
                    (logged_in["account_id"],),
                ).fetchone()
                if existing:
                    raise AuthError("无法完成注册，请改用登录或找回密码。", 409,
                                    "registration_unavailable")
                conn.execute(
                    """INSERT INTO auth_password_credentials
                       (account_id,password_hash,created_at,updated_at)
                       VALUES(?,?,?,?)""",
                    (logged_in["account_id"], payload["password_hash"], now, now),
                )
        except Exception:
            self.revoke_session(logged_in.get("token"))
            raise
        return logged_in

    def resend_registration(self, session_token: str, challenge_id: str) -> dict:
        """Issue a fresh code without asking the user to re-enter a password.

        The original challenge contains only an Argon2id password hash and is
        already bound to this pre-auth browser session. The shared challenge
        creator enforces cooldown and rate limits, and consumes the old code.
        """
        session = self.authenticate_session(session_token)
        if not session or session["authenticated"]:
            raise AuthError("请刷新页面后重试。", 401,
                            "preauth_session_required")
        if not isinstance(challenge_id, str):
            raise AuthError("验证请求无效，请重新注册。", 400,
                            "invalid_registration_challenge")
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT email,payload_json FROM auth_email_challenges
                   WHERE id=? AND session_hash=? AND purpose='register'""",
                (challenge_id, session["token_hash"]),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise AuthError("验证请求无效，请重新注册。", 400,
                            "invalid_registration_challenge")
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError as exc:
            raise AuthError("验证请求无效，请重新注册。", 400,
                            "invalid_registration_challenge") from exc
        if not isinstance(payload.get("password_hash"), str):
            raise AuthError("验证请求无效，请重新注册。", 400,
                            "invalid_registration_challenge")
        return self._begin_email_challenge(
            session_token, row["email"], "register", payload,
            delivery_required=True,
        )

    def login_password(self, session_token: str, email: str, password: str) -> dict:
        session = self.authenticate_session(session_token)
        if not session or session["authenticated"]:
            raise AuthError("登录会话已失效，请刷新后重试。", 401,
                            "preauth_session_required")
        try:
            normalized = normalize_email(email)
        except AuthError:
            normalized = "invalid@example.invalid"
        candidate = password if isinstance(password, str) else ""
        now = int(self._now())
        session_hash = session["token_hash"]
        email_key = self._email_key(normalized)
        failed = False
        logged_in = None
        with self._transaction() as conn:
            live_session = conn.execute(
                """SELECT 1 FROM auth_sessions
                   WHERE token_hash=? AND authenticated=0
                     AND revoked_at IS NULL AND expires_at>?""",
                (session_hash, now),
            ).fetchone()
            if not live_session:
                raise AuthError("登录会话已失效，请刷新后重试。", 401,
                                "preauth_session_required")
            failures = conn.execute(
                """SELECT COUNT(*) AS n FROM auth_login_attempts
                   WHERE succeeded=0 AND created_at>? AND (email_key=? OR session_hash=?)""",
                (now - 15 * 60, email_key, session_hash),
            ).fetchone()["n"]
            if int(failures) >= 10:
                raise AuthError("登录尝试过于频繁，请稍后重试。", 429,
                                "login_rate_limited", 15 * 60)
            credential = conn.execute(
                """SELECT e.account_id,c.password_hash FROM auth_verified_emails e
                   JOIN auth_password_credentials c ON c.account_id=e.account_id
                   WHERE e.email=?""",
                (normalized,),
            ).fetchone()
            stored_hash = credential["password_hash"] if credential else self._dummy_password_hash
            try:
                valid = self.password_hasher.verify(stored_hash, candidate)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                valid = False
            valid = bool(valid and credential)
            conn.execute(
                """INSERT INTO auth_login_attempts
                   (email_key,session_hash,succeeded,created_at) VALUES(?,?,?,?)""",
                (email_key, session_hash, int(valid), now),
            )
            if not valid:
                failed = True
            else:
                if self.password_hasher.check_needs_rehash(stored_hash):
                    conn.execute(
                        """UPDATE auth_password_credentials
                           SET password_hash=?,updated_at=? WHERE account_id=?""",
                        (self.password_hasher.hash(candidate), now, credential["account_id"]),
                    )
                consumed = conn.execute(
                    """UPDATE auth_sessions SET revoked_at=?
                       WHERE token_hash=? AND authenticated=0
                         AND revoked_at IS NULL AND expires_at>?""",
                    (now, session_hash, now),
                )
                if consumed.rowcount != 1:
                    raise AuthError("登录会话已失效，请刷新后重试。", 401,
                                    "preauth_session_required")
                logged_in = self._new_session(
                    conn, credential["account_id"], True, now,
                )
                logged_in["user"] = self._profile_user(conn, credential["account_id"])
        if failed:
            raise AuthError("邮箱或密码错误。", 401, "invalid_credentials")
        return logged_in

    def begin_password_reset(self, session_token: str, email: str) -> dict:
        normalized = normalize_email(email)
        conn = self._connect()
        try:
            credential = conn.execute(
                """SELECT e.account_id FROM auth_verified_emails e
                   JOIN auth_password_credentials c ON c.account_id=e.account_id
                   WHERE e.email=?""",
                (normalized,),
            ).fetchone()
        finally:
            conn.close()
        return self._begin_email_challenge(
            session_token, normalized, "password_reset",
            {"account_id": credential["account_id"] if credential else None,
             "eligible": credential is not None},
            delivery_required=credential is not None,
        )

    def reset_password(self, session_token: str, challenge_id: str, code: str,
                       new_password: str) -> dict:
        password_hash = self.password_hasher.hash(validate_password(new_password))
        verified = self._verify_email_challenge(
            session_token, challenge_id, code, "password_reset",
        )
        payload = verified["payload"]
        account_id = payload.get("account_id")
        if not payload.get("eligible") or not isinstance(account_id, str):
            raise AuthError("验证码无效或已过期。", 400,
                            "invalid_or_expired_code")
        now = int(self._now())
        with self._transaction() as conn:
            mapping = conn.execute(
                "SELECT account_id FROM auth_verified_emails WHERE email=?",
                (verified["email"],),
            ).fetchone()
            if not mapping or mapping["account_id"] != account_id:
                raise AuthError("验证码无效或已过期。", 400,
                                "invalid_or_expired_code")
            updated = conn.execute(
                """UPDATE auth_password_credentials
                   SET password_hash=?,updated_at=? WHERE account_id=?""",
                (password_hash, now, account_id),
            )
            if updated.rowcount != 1:
                raise AuthError("验证码无效或已过期。", 400,
                                "invalid_or_expired_code")
            # Password reset is a security event: revoke every existing device,
            # including the pre-auth flow, then issue one fresh session.
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE account_id=? AND revoked_at IS NULL",
                (now, account_id),
            )
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                (now, _token_hash(session_token)),
            )
            logged_in = self._new_session(conn, account_id, True, now)
            logged_in["user"] = self._profile_user(conn, account_id)
        return logged_in

    def rotate_authenticated(self, old_token: str, provider: str, subject: str,
                             email: str, display_name: str = "",
                             avatar_url: str = "") -> dict:
        """Link a verified identity and replace the pre-auth session atomically."""
        if provider not in {"email", "google"}:
            raise AuthError("登录方式不受支持。", code="unsupported_provider")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise AuthError("身份凭据无效。", code="invalid_identity")
        normalized = normalize_email(email)
        old_hash = _token_hash(old_token)
        now = int(self._now())
        display_name = unicodedata.normalize("NFKC", display_name or "").strip()[:120]
        avatar_url = (avatar_url or "").strip()[:2048]
        with self._transaction() as conn:
            old = conn.execute(
                """SELECT * FROM auth_sessions
                   WHERE token_hash=? AND revoked_at IS NULL AND expires_at>?""",
                (old_hash, now),
            ).fetchone()
            if not old or bool(old["authenticated"]):
                raise AuthError("登录会话已失效，请刷新后重试。", 401,
                                "preauth_session_required")

            identity = conn.execute(
                """SELECT account_id,verified_email FROM auth_identities
                   WHERE provider=? AND subject=?""",
                (provider, subject),
            ).fetchone()
            if identity:
                account_id = identity["account_id"]
                # Provider subjects are stable; a changed claim must not
                # silently turn a newly supplied/recycled mailbox into another
                # login alias.  Email changes need a dedicated re-verification
                # flow, so keep the identity's previously verified mailbox.
                normalized = identity["verified_email"]
            else:
                verified = conn.execute(
                    "SELECT account_id FROM auth_verified_emails WHERE email=?",
                    (normalized,),
                ).fetchone()
                if verified:
                    account_id = verified["account_id"]
                else:
                    # Pre-auth sessions share a non-billable placeholder.  A
                    # first verified identity receives its own durable account.
                    account_id = "acct_" + secrets.token_hex(24)
                    self._insert_account(conn, account_id, now)
                    conn.execute(
                        """INSERT INTO auth_verified_emails(email,account_id,verified_at)
                           VALUES(?,?,?)""",
                        (normalized, account_id, now),
                    )
                conn.execute(
                    """INSERT INTO auth_identities
                       (provider,subject,account_id,verified_email,created_at,updated_at)
                       VALUES(?,?,?,?,?,?)""",
                    (provider, subject, account_id, normalized, now, now),
                )

            # A stable provider subject wins over an email later changed at the
            # provider.  Never move an existing identity to another account.
            linked_email = conn.execute(
                "SELECT account_id FROM auth_verified_emails WHERE email=?",
                (normalized,),
            ).fetchone()
            if linked_email and linked_email["account_id"] != account_id:
                raise AuthError("该邮箱已绑定其他账户。", 409, "identity_conflict")
            conn.execute(
                """INSERT OR IGNORE INTO auth_verified_emails(email,account_id,verified_at)
                   VALUES(?,?,?)""",
                (normalized, account_id, now),
            )
            profile = conn.execute(
                "SELECT * FROM auth_profiles WHERE account_id=?", (account_id,),
            ).fetchone()
            if profile:
                next_name = display_name or profile["display_name"]
                next_avatar = avatar_url or profile["avatar_url"]
                conn.execute(
                    """UPDATE auth_profiles
                       SET primary_email=?,display_name=?,avatar_url=?,updated_at=?
                       WHERE account_id=?""",
                    (normalized, next_name, next_avatar, now, account_id),
                )
            else:
                conn.execute(
                    """INSERT INTO auth_profiles
                       (account_id,primary_email,display_name,avatar_url,created_at,updated_at)
                       VALUES(?,?,?,?,?,?)""",
                    (account_id, normalized, display_name, avatar_url, now, now),
                )
            conn.execute(
                "UPDATE auth_sessions SET revoked_at=? WHERE token_hash=?",
                (now, old_hash),
            )
            new_session = self._new_session(conn, account_id, True, now)
            new_session["user"] = self._profile_user(conn, account_id)
        return new_session

    def create_oauth_flow(self, session_token: str, return_to: str,
                          redirect_uri: str) -> dict:
        session = self.authenticate_session(session_token)
        if not session or session["authenticated"]:
            raise AuthError("请刷新页面后重试。", 401, "preauth_session_required")
        now = int(self._now())
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        with self._transaction() as conn:
            conn.execute(
                """INSERT INTO auth_oauth_flows
                   (state_hash,session_hash,nonce,code_verifier,redirect_uri,return_to,
                    created_at,expires_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (_token_hash(state), session["token_hash"], nonce, verifier,
                 redirect_uri, safe_return_to(return_to), now, now + OAUTH_FLOW_SECONDS),
            )
            self._purge(conn, now)
        return {
            "state": state,
            "nonce": nonce,
            "code_verifier": verifier,
            "code_challenge": challenge,
            "redirect_uri": redirect_uri,
            "return_to": safe_return_to(return_to),
        }

    def consume_oauth_flow(self, session_token: str, state: str) -> dict:
        session = self.authenticate_session(session_token)
        if not session or session["authenticated"] or not isinstance(state, str):
            raise AuthError("Google 登录请求已失效。", 400, "invalid_oauth_state")
        now = int(self._now())
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM auth_oauth_flows WHERE state_hash=?",
                (_token_hash(state),),
            ).fetchone()
            invalid = (not row or row["session_hash"] != session["token_hash"]
                       or row["consumed_at"] is not None
                       or int(row["expires_at"]) <= now)
            if invalid:
                raise AuthError("Google 登录请求已失效。", 400,
                                "invalid_oauth_state")
            updated = conn.execute(
                "UPDATE auth_oauth_flows SET consumed_at=? WHERE state_hash=? AND consumed_at IS NULL",
                (now, row["state_hash"]),
            )
            if updated.rowcount != 1:
                raise AuthError("Google 登录请求已失效。", 400,
                                "invalid_oauth_state")
            return dict(row)


@dataclass
class EmailDelivery:
    mode: str
    sender: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_ssl: bool = False
    smtp_starttls: bool = True
    smtp_proxy_url: str = ""
    _queue: queue.Queue = field(init=False, repr=False)

    def __post_init__(self):
        self._queue = queue.Queue(maxsize=512)
        for index in range(2):
            worker = threading.Thread(
                target=self._delivery_worker,
                name=f"rightthesis-email-{index + 1}",
                daemon=True,
            )
            worker.start()

    @classmethod
    def from_env(cls) -> "EmailDelivery":
        mode = os.environ.get("AUTH_EMAIL_DELIVERY", "console").strip().lower()
        if mode not in {"console", "smtp", "disabled"}:
            raise RuntimeError("AUTH_EMAIL_DELIVERY 必须是 console、smtp 或 disabled")
        try:
            port = int(os.environ.get("AUTH_SMTP_PORT", "587"))
        except ValueError as exc:
            raise RuntimeError("AUTH_SMTP_PORT 必须是整数") from exc
        proxy_url = os.environ.get("AUTH_SMTP_PROXY_URL", "").strip()
        if proxy_url:
            proxy = urlsplit(proxy_url)
            try:
                proxy_port = proxy.port
            except ValueError as exc:
                raise RuntimeError("AUTH_SMTP_PROXY_URL 端口无效") from exc
            if (proxy.scheme != "http" or not proxy.hostname or not proxy_port
                    or proxy.username or proxy.password or proxy.path not in {"", "/"}
                    or proxy.query or proxy.fragment):
                raise RuntimeError(
                    "AUTH_SMTP_PROXY_URL 只接受不含凭据的 http://主机:端口")
        return cls(
            mode=mode,
            sender=os.environ.get("AUTH_EMAIL_FROM", "").strip(),
            smtp_host=os.environ.get("AUTH_SMTP_HOST", "").strip(),
            smtp_port=port,
            smtp_username=os.environ.get("AUTH_SMTP_USERNAME", "").strip(),
            smtp_password=os.environ.get("AUTH_SMTP_PASSWORD", ""),
            smtp_ssl=os.environ.get("AUTH_SMTP_SSL", "0").lower() in {"1", "true", "yes", "on"},
            smtp_starttls=os.environ.get("AUTH_SMTP_STARTTLS", "1").lower() in {"1", "true", "yes", "on"},
            smtp_proxy_url=proxy_url,
        )

    @property
    def configured(self) -> bool:
        if self.mode == "console":
            return True
        return self.mode == "smtp" and bool(
            self.sender and self.smtp_host and self.smtp_username
            and self.smtp_password and (self.smtp_ssl or self.smtp_starttls)
            and (not self.smtp_proxy_url or self.smtp_ssl)
        )

    def send_code(self, email: str, code: str, purpose: str = "register",
                  expires_minutes: int = 10, deliver: bool = True,
                  wait_for_delivery: bool = False):
        """Deliver registration mail or queue reset mail without disclosure.

        Unknown-mailbox reset requests enqueue the same shaped task with
        ``deliver=False``.  A small bounded queue avoids unbounded memory use
        when a mail provider is slow or unavailable.
        """
        if deliver and not self.configured:
            raise AuthError("邮箱登录服务配置不完整。", 503,
                            "email_login_unavailable")
        # Registration may report a delivery failure to its owner immediately.
        # Password reset remains queued so SMTP latency cannot disclose whether
        # the requested mailbox belongs to an account.
        if deliver and wait_for_delivery:
            self._deliver_code(email, code, purpose, expires_minutes)
            return
        try:
            self._queue.put_nowait((bool(deliver), email, code, purpose,
                                    expires_minutes))
        except queue.Full as exc:
            raise AuthError("邮件队列繁忙，请稍后重试。", 503,
                            "email_delivery_busy") from exc

    def _delivery_worker(self):
        while True:
            deliver, email, code, purpose, expires_minutes = self._queue.get()
            try:
                if deliver:
                    self._deliver_code(email, code, purpose, expires_minutes)
            except AuthError as exc:
                # Never print the code or SMTP credential.  The challenge can
                # safely expire or be replaced by the resend flow.
                print(f"[RightThesis 邮件投递失败] {email}: {exc}", flush=True)
            finally:
                self._queue.task_done()

    def _deliver_code(self, email: str, code: str, purpose: str,
                      expires_minutes: int):
        if self.mode == "disabled":
            raise AuthError("邮箱登录服务尚未配置。", 503, "email_login_unavailable")
        if self.mode == "console":
            label = "重置密码" if purpose == "password_reset" else "注册"
            print(f"[RightThesis 本地{label}验证] {email} 验证码: {code}"
                  f" ({expires_minutes} 分钟内有效)", flush=True)
            return
        if not self.configured:
            raise AuthError("邮箱登录服务配置不完整。", 503,
                            "email_login_unavailable")
        message = EmailMessage()
        action = "重置密码" if purpose == "password_reset" else "完成注册"
        message["Subject"] = f"RightThesis {action}验证码"
        message["From"] = self.sender
        message["To"] = email
        message.set_content(
            f"你的 RightThesis {action}验证码是：{code}\n\n"
            f"验证码在 {expires_minutes} 分钟内有效，且只能使用一次。\n"
            "如果不是你本人操作，请忽略这封邮件。\n"
        )
        try:
            tls_context = ssl.create_default_context(cafile=certifi.where())
            if self.smtp_ssl:
                if self.smtp_proxy_url:
                    proxy = urlsplit(self.smtp_proxy_url)
                    client = _HTTPConnectSMTP_SSL(
                        self.smtp_host, self.smtp_port, timeout=15,
                        context=tls_context, proxy_host=proxy.hostname,
                        proxy_port=proxy.port,
                    )
                else:
                    client = smtplib.SMTP_SSL(
                        self.smtp_host, self.smtp_port, timeout=15,
                        context=tls_context,
                    )
            else:
                client = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
            with client:
                if not self.smtp_ssl and self.smtp_starttls:
                    client.starttls(context=tls_context)
                if self.smtp_username:
                    client.login(self.smtp_username, self.smtp_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException, http.client.HTTPException) as exc:
            raise AuthError("验证邮件发送失败，请稍后重试。", 503,
                            "email_delivery_failed") from exc


class _HTTPConnectSMTP_SSL(smtplib.SMTP_SSL):
    """Reach an SSL-only SMTP host through an explicitly configured proxy."""

    def __init__(self, host, port, *, timeout, context, proxy_host, proxy_port):
        self._proxy_host = proxy_host
        self._proxy_port = proxy_port
        super().__init__(host, port, timeout=timeout, context=context)

    def _get_socket(self, host, port, timeout):
        tunnel = http.client.HTTPConnection(
            self._proxy_host, self._proxy_port, timeout=timeout,
        )
        try:
            tunnel.set_tunnel(host, port)
            tunnel.connect()
            return self.context.wrap_socket(tunnel.sock, server_hostname=host)
        except Exception:
            tunnel.close()
            raise


class GoogleOAuthClient:
    AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

    def __init__(self, client_id: str = "", client_secret: str = ""):
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()

    @classmethod
    def from_env(cls) -> "GoogleOAuthClient":
        return cls(
            os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
            or os.environ.get("GOOGLE_CLIENT_ID", ""),
            os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
            or os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        )

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def authorization_url(self, flow: dict) -> str:
        if not self.configured:
            raise AuthError("Google 登录尚未配置。", 503, "google_unavailable")
        return self.AUTHORIZATION_ENDPOINT + "?" + urlencode({
            "client_id": self.client_id,
            "redirect_uri": flow["redirect_uri"],
            "response_type": "code",
            "scope": "openid email profile",
            "state": flow["state"],
            "nonce": flow["nonce"],
            "code_challenge": flow["code_challenge"],
            "code_challenge_method": "S256",
            "prompt": "select_account",
        })

    def exchange_and_verify(self, code: str, flow: dict) -> dict:
        if not self.configured:
            raise AuthError("Google 登录尚未配置。", 503, "google_unavailable")
        if not isinstance(code, str) or not code:
            raise AuthError("Google 未返回有效授权码。", 400, "google_callback_failed")
        body = urlencode({
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": flow["redirect_uri"],
            "grant_type": "authorization_code",
            "code_verifier": flow["code_verifier"],
        }).encode("ascii")
        request = UrlRequest(
            self.TOKEN_ENDPOINT, data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"},
        )
        try:
            # python.org's macOS Python can have no default OpenSSL CA file.
            # certifi provides a verified CA bundle without disabling TLS checks.
            tls_context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(request, timeout=15, context=tls_context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                details = json.loads(exc.read(4096).decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                details = {}
            reason = details.get("error") if isinstance(details, dict) else None
            known_errors = {
                "invalid_client": "google_client_invalid",
                "invalid_grant": "google_authorization_expired",
                "redirect_uri_mismatch": "google_redirect_invalid",
            }
            code = known_errors.get(reason, "google_token_exchange_failed")
            # Do not log the authorization code, ID token or client secret.
            print(f"[RightThesis Google OAuth] token exchange HTTP {exc.code}: {code}",
                  flush=True)
            raise AuthError("Google 登录校验失败。", 400, code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            print(f"[RightThesis Google OAuth] token exchange network: "
                  f"{type(exc).__name__}", flush=True)
            raise AuthError("无法连接 Google 登录服务。", 503,
                            "google_network_error") from exc
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise AuthError("Google 登录响应无效。", 400,
                            "google_token_invalid") from exc
        raw_id_token = payload.get("id_token") if isinstance(payload, dict) else None
        if not isinstance(raw_id_token, str):
            raise AuthError("Google 未返回身份令牌。", 400,
                            "google_token_invalid")
        try:
            from google.auth.exceptions import TransportError
            from google.auth.transport.requests import Request as GoogleRequest
            from google.oauth2 import id_token
        except ImportError as exc:
            raise AuthError("Google 身份校验组件不可用。", 503,
                            "google_unavailable") from exc
        try:
            claims = id_token.verify_oauth2_token(
                raw_id_token, GoogleRequest(), self.client_id,
            )
        except TransportError as exc:
            print("[RightThesis Google OAuth] ID token certificate network failure",
                  flush=True)
            raise AuthError("无法获取 Google 身份验证证书。", 503,
                            "google_network_error") from exc
        except (ValueError, TypeError) as exc:
            raise AuthError("Google 登录校验失败。", 400,
                            "google_token_invalid") from exc
        verified = claims.get("email_verified")
        if (claims.get("nonce") != flow["nonce"]
                or verified not in {True, "true", "True"}
                or not isinstance(claims.get("sub"), str)
                or not isinstance(claims.get("email"), str)):
            raise AuthError("Google 账户未提供已验证邮箱。", 400,
                            "google_identity_invalid")
        return {
            "provider": "google",
            "subject": claims["sub"],
            "email": normalize_email(claims["email"]),
            "display_name": str(claims.get("name") or "")[:120],
            "avatar_url": str(claims.get("picture") or "")[:2048],
        }

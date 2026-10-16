"""Signed anonymous sessions for the local trial mode.

Each browser receives a high-entropy anonymous account in an HttpOnly cookie,
while CSRF and account ownership checks continue to protect write operations
and background jobs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Callable, Optional


COOKIE_NAME = "humanizer_trial_session"


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def load_or_create_secret(path: Path | str, env_value: Optional[str] = None) -> bytes:
    """Return a >=256-bit signing secret, creating a mode-0600 file if needed."""
    if env_value:
        raw = env_value.encode("utf-8")
        if len(raw) < 32:
            raise RuntimeError("TRIAL_SESSION_SECRET 至少需要 32 个字节")
        return raw

    secret_path = Path(path)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raw = secret_path.read_bytes()
        if len(raw) < 32:
            raise RuntimeError(f"会话密钥文件过短：{secret_path}")
        return raw
    raw = secrets.token_bytes(48)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            secret_path.unlink()
        except OSError:
            pass
        raise
    return raw


class TrialSessionStore:
    def __init__(self, secret: bytes, session_seconds: int = 7 * 24 * 60 * 60,
                 now: Optional[Callable[[], float]] = None):
        if len(secret) < 32:
            raise ValueError("session secret must contain at least 32 bytes")
        self.secret = secret
        self.session_seconds = max(300, int(session_seconds))
        self._now = now or time.time

    @staticmethod
    def _user(account_id: str) -> dict[str, str]:
        return {
            "id": account_id,
            "account_id": account_id,
            "name": "匿名访客",
            "display_name": "匿名访客",
            "label": "匿名访客",
            "kind": "guest",
        }

    def _issue_session(self, account_id: str) -> dict:
        now = int(self._now())
        csrf = secrets.token_urlsafe(24)
        payload = {
            "v": 1,
            "kind": "guest",
            "account_id": account_id,
            "iat": now,
            "exp": now + self.session_seconds,
            "csrf": csrf,
            "sid": secrets.token_urlsafe(18),
        }
        packed = _b64encode(json.dumps(
            payload, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8"))
        signature = _b64encode(hmac.new(
            self.secret, packed.encode("ascii"), hashlib.sha256,
        ).digest())
        return {
            "token": packed + "." + signature,
            "csrf_token": csrf,
            "user": self._user(account_id),
            "expires_at": payload["exp"],
            "kind": "guest",
        }

    def create_guest(self) -> dict:
        """Create a signed anonymous identity with 192 bits of entropy."""
        return self._issue_session("guest_" + secrets.token_hex(24))

    def authenticate(self, token: str) -> Optional[dict]:
        if not isinstance(token, str) or token.count(".") != 1:
            return None
        packed, supplied = token.split(".", 1)
        expected = _b64encode(hmac.new(
            self.secret, packed.encode("ascii"), hashlib.sha256,
        ).digest())
        if not hmac.compare_digest(supplied, expected):
            return None
        try:
            payload = json.loads(_b64decode(packed))
        except (ValueError, TypeError, json.JSONDecodeError):
            return None
        now = int(self._now())
        account_id = payload.get("account_id") if isinstance(payload, dict) else None
        if (not isinstance(payload, dict) or payload.get("v") != 1
                or payload.get("kind") != "guest"
                or not isinstance(payload.get("exp"), int)
                or payload["exp"] <= now
                or not isinstance(payload.get("csrf"), str)
                or not isinstance(account_id, str)
                or not re.fullmatch(r"guest_[0-9a-f]{48}", account_id)):
            return None
        return {
            "account_id": account_id,
            "csrf_token": payload["csrf"],
            "expires_at": payload["exp"],
            "kind": "guest",
            "user": self._user(account_id),
        }

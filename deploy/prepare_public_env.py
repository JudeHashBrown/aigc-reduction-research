"""Prepare a minimal production .env without copying local data or proxy settings.

The output contains secrets. Never print it or add it to a source archive.
"""

import os
import sys
from pathlib import Path


COPY_KEYS = (
    "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
    "AUTH_EMAIL_FROM", "AUTH_SMTP_USERNAME", "AUTH_SMTP_PASSWORD",
    "AUTH_SMTP_HOST", "AUTH_SMTP_PORT", "AUTH_SMTP_SSL", "AUTH_SMTP_STARTTLS",
    "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
)
REQUIRED_KEYS = (
    "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "AUTH_EMAIL_FROM",
    "AUTH_SMTP_USERNAME", "AUTH_SMTP_PASSWORD", "AUTH_SMTP_HOST",
    "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET",
)
FIXED = {
    "AUTH_MODE": "accounts",
    "AUTH_SESSION_SECRET_FILE": "data/auth_session_secret",
    "AUTH_SESSION_DAYS": "30",
    "AUTH_EMAIL_DELIVERY": "smtp",
    "PUBLIC_ORIGIN": "https://rightthesis.com",
    "GOOGLE_OAUTH_REDIRECT_URI": "https://rightthesis.com/api/auth/google/callback",
    "PAYMENT_PROVIDER": "stripe",
}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_public_env.py source.env destination.env")
    source, destination = map(Path, sys.argv[1:])
    values = {}
    for raw in source.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() in COPY_KEYS:
            values[key.strip()] = value.strip()
    missing = [key for key in REQUIRED_KEYS if not values.get(key)]
    if missing:
        raise SystemExit("missing required settings: " + ", ".join(missing))
    if destination.exists():
        raise SystemExit("destination already exists; refusing to overwrite")
    lines = [f"{key}={values[key]}" for key in COPY_KEYS if key in values]
    lines += [f"{key}={value}" for key, value in FIXED.items()]
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    print("Prepared production configuration (values hidden).")


if __name__ == "__main__":
    main()

"""Signed anonymous-session and trial-entitlement tests."""
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

from billing import BillingStore  # noqa: E402
from trial_session import TrialSessionStore, load_or_create_secret  # noqa: E402


def run():
    with tempfile.TemporaryDirectory() as folder_name:
        folder = Path(folder_name)
        secret_path = folder / "session-secret"
        secret = load_or_create_secret(secret_path)
        assert len(secret) >= 32
        assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600
        assert load_or_create_secret(secret_path) == secret

        sessions = TrialSessionStore(secret)
        guest_a = sessions.create_guest()
        guest_b = sessions.create_guest()
        account_a = guest_a["user"]["account_id"]
        account_b = guest_b["user"]["account_id"]
        assert guest_a["user"]["kind"] == "guest"
        assert account_a.startswith("guest_")
        assert account_a != account_b

        restored = sessions.authenticate(guest_a["token"])
        assert restored is not None
        assert restored["account_id"] == account_a
        assert restored["csrf_token"] == guest_a["csrf_token"]
        assert sessions.authenticate(guest_a["token"] + "tampered") is None
        other_secret = TrialSessionStore(os.urandom(48))
        assert other_secret.authenticate(guest_a["token"]) is None

        clock = [1000.0]
        expiring = TrialSessionStore(
            secret, session_seconds=300, now=lambda: clock[0],
        )
        short_lived = expiring.create_guest()
        assert expiring.authenticate(short_lived["token"]) is not None
        clock[0] = 1300.0
        assert expiring.authenticate(short_lived["token"]) is None

        billing = BillingStore(folder / "billing.sqlite3")
        summary_a = billing.grant_trial(account_a, 3000, 3000)
        summary_b = billing.grant_trial(account_b, 3000, 3000)
        assert summary_a["balance"] == summary_b["balance"] == 3000
        assert summary_a["account_id"] == account_a
        assert summary_b["account_id"] == account_b
        assert summary_a["max_chars_per_job"] == 3000
        assert summary_a["allowed_strengths"] == [
            "conservative", "balanced", "deep",
        ]
        assert summary_a["plan_id"] == "trial"
        assert billing.grant_trial(account_a, 3000, 3000)["balance"] == 3000
        trial_entries = [
            entry for entry in billing.ledger(account_a, 20)
            if entry["reference"] == "trial:v1"
        ]
        assert len(trial_entries) == 1


if __name__ == "__main__":
    run()
    print("✓ 匿名会话：签名、防篡改、过期与独立 3000 字额度全部正确")

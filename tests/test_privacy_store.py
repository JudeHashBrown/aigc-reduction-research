"""Account export and deletion-request checks without real users or payments."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))

from auth import AuthStore  # noqa: E402
from billing import BillingStore  # noqa: E402
from privacy_store import PrivacyError, PrivacyStore  # noqa: E402
from workspace_store import WorkspaceStore  # noqa: E402


def test_export_and_safe_deletion():
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "app.sqlite3"
        billing = BillingStore(database)
        workspace = WorkspaceStore(database)
        auth = AuthStore(database, b"test-secret-more-than-thirty-two-bytes")
        privacy = PrivacyStore(database)
        preauth = auth.create_pre_auth()
        session = auth.rotate_authenticated(
            preauth["token"], provider="google", subject="google-test-123",
            email="writer@example.com", display_name="Writer",
        )
        account = session["account_id"]
        workspace.create_manuscript(account, {
            "name": "Thesis", "kind": "text", "source": "private draft",
            "current": "final draft", "notices": [],
        })
        billing.summary(account)
        exported = privacy.export(account)
        assert exported["profile"]["primary_email"] == "writer@example.com"
        assert exported["manuscripts"][0]["source"] == "private draft"
        assert "auth_sessions" not in exported
        assert "auth_password_credentials" not in exported
        try:
            privacy.request_deletion(account, "different@example.com")
        except PrivacyError as exc:
            assert exc.status == 400
        else:
            raise AssertionError("deletion request needs the account email")
        requested = privacy.request_deletion(account, "writer@example.com")
        assert requested["status"] == "pending"
        assert privacy.request_deletion(account, "writer@example.com")["id"] == requested["id"]
        assert privacy.cancel_deletion(account)["status"] == "cancelled"
        requested = privacy.request_deletion(account, "writer@example.com")
        assert privacy.complete_deletion(requested["id"])["status"] == "completed"
        assert auth.authenticate_session(session["token"]) is None
        assert workspace.list_manuscripts(account) == []
        assert privacy.current_request(account)["status"] == "completed"
        try:
            privacy.export(account)
        except PrivacyError as exc:
            assert exc.status == 404
        else:
            raise AssertionError("deleted account must not export content")


def test_paid_entitlements_block_deletion():
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / "app.sqlite3"
        billing = BillingStore(database)
        WorkspaceStore(database)
        auth = AuthStore(database, b"test-secret-more-than-thirty-two-bytes")
        privacy = PrivacyStore(database)
        session = auth.rotate_authenticated(
            auth.create_pre_auth()["token"], provider="google", subject="paid-user",
            email="paid@example.com",
        )
        account = session["account_id"]
        billing.mock_checkout(account, "pack_3k", "privacy_paid_001")
        requested = privacy.request_deletion(account, "paid@example.com")
        try:
            privacy.complete_deletion(requested["id"])
        except PrivacyError as exc:
            assert exc.status == 409
        else:
            raise AssertionError("unused paid credits must not disappear on account deletion")
        assert auth.authenticate_session(session["token"])


if __name__ == "__main__":
    test_export_and_safe_deletion()
    test_paid_entitlements_block_deletion()
    print("✓ 账户数据导出、删除申请、取消及权益保护")

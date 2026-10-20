"""Admin summaries are bounded and never reveal manuscript bodies or credentials."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
from admin_store import AdminStore  # noqa: E402
from auth import AuthStore  # noqa: E402
from billing import BillingStore  # noqa: E402
from workspace_store import WorkspaceStore  # noqa: E402


def run():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "state.sqlite3"
        billing = BillingStore(path)
        workspaces = WorkspaceStore(path)
        auth = AuthStore(path, b"test-admin-secret-at-least-32-bytes")
        session = auth.rotate_authenticated(
            auth.create_pre_auth()["token"], provider="google", subject="admin-test",
            email="test@example.com")
        account = session["account_id"]
        workspaces.create_manuscript(account, {
            "name": "private", "kind": "text", "source": "PRIVATE MANUSCRIPT BODY",
            "current": "PRIVATE MANUSCRIPT BODY", "notices": [],
        })
        billing.summary(account)
        admin = AdminStore(path)
        users = admin.users()
        assert len(users) == 1 and users[0]["manuscript_count"] == 1
        assert "PRIVATE MANUSCRIPT BODY" not in str(users)
        assert "password" not in str(users).lower()
        assert admin.jobs() == []
        assert admin.economics()["model_cost_available"] is False
        assert admin.service()["controls_available"] is False


if __name__ == "__main__":
    run()
    print("✓ 运营摘要只读且不泄露文稿正文")

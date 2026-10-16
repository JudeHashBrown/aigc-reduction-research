"""HTTP round-trip: manuscripts, DOCX bytes, restart, and saved jobs."""
import base64
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from http_test_utils import free_port, opener_with_cookies, request, stop_server, wait_until_ready
from test_docx import make_docx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
from billing import BillingStore  # noqa: E402
from workspace_store import WorkspaceStore  # noqa: E402


class WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.opener, _ = opener_with_cookies()
        self.env = os.environ.copy()
        self.env.update({"AUTH_MODE": "local", "TRIAL_MODE": "0",
                         "BILLING_DB": str(Path(self.temp.name) / "state.sqlite3"),
                         "PAYMENT_PROVIDER": "mock", "LLM_BASE_URL": "http://127.0.0.1:1/v1",
                         "LLM_API_KEY": "test-only-not-used"})
        self.start()

    def tearDown(self):
        stop_server(self.proc)
        if self.proc.stdout:
            self.proc.stdout.close()
        self.temp.cleanup()

    def start(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / "web/server.py"), str(self.port)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=self.env)
        wait_until_ready(self.opener, self.base, self.proc)

    def call(self, path, payload=None):
        return request(self.opener, self.base, path, payload)

    def test_import_save_restart_and_export_original_docx(self):
        original = make_docx(["Original research sentence."], split_runs=True)
        b64 = base64.b64encode(original).decode("ascii")
        code, extracted, _ = self.call("/api/docx/extract", {"file": b64})
        self.assertEqual(code, 200)
        code, created, _ = self.call("/api/documents", {
            "name": "thesis.docx", "kind": "docx", "source": extracted["text"],
            "current": extracted["text"], "report": None, "notices": [],
            "document": {"name": "thesis.docx", "kind": "docx", "data": b64, "meta": {}},
        })
        self.assertEqual(code, 201, created)
        manuscript_id = created["document"]["id"]
        code, saved, _ = self.call(f"/api/documents/{manuscript_id}/save", {
            "revision": 1, "current": "Revised research sentence.",
            "report": None, "notices": [],
        })
        self.assertEqual(code, 200, saved)
        code, conflict, _ = self.call(f"/api/documents/{manuscript_id}/save", {
            "revision": 1, "current": "stale edit", "report": None, "notices": [],
        })
        self.assertEqual((code, conflict.get("code")), (409, "conflict"))
        stop_server(self.proc)
        if self.proc.stdout:
            self.proc.stdout.close()
        self.start()
        code, fetched, _ = self.call(f"/api/documents/{manuscript_id}")
        self.assertEqual(code, 200)
        doc = fetched["document"]
        self.assertEqual(doc["current"], "Revised research sentence.")
        self.assertEqual(base64.b64decode(doc["document"]["data"]), original)
        code, exported, _ = self.call("/api/docx/export", {
            "file": doc["document"]["data"], "text": doc["current"],
        })
        self.assertEqual(code, 200, exported)
        code, reread, _ = self.call("/api/docx/extract", {"file": exported["file"]})
        self.assertEqual((code, reread["text"]), (200, "Revised research sentence."))
        code, listing, _ = self.call("/api/documents")
        self.assertEqual([item["id"] for item in listing["documents"]], [manuscript_id])

    def test_restart_recovers_saved_result_and_refunds_interrupted_job(self):
        stop_server(self.proc)
        if self.proc.stdout:
            self.proc.stdout.close()
        db_path = Path(self.env["BILLING_DB"])
        billing = BillingStore(db_path)
        jobs = WorkspaceStore(db_path)
        account = "local-demo"
        completed_id = "job_" + "b" * 24
        interrupted_id = "job_" + "c" * 24
        jobs.claim_job(account, "request_done", "hash-done", completed_id, 2)
        billing.reserve(account, completed_id, "原稿", "conservative")
        jobs.update_job(completed_id, result={"text": "修改稿", "n_accepted": 1},
                        phase="finalizing")
        jobs.claim_job(account, "request_lost", "hash-lost", interrupted_id, 2)
        billing.reserve(account, interrupted_id, "待修改", "conservative")
        # Pretend the process that owned these claims died before restart.
        with sqlite3.connect(db_path) as db:
            db.execute("UPDATE rewrite_jobs SET owner_pid=? WHERE id IN (?, ?)",
                       (999999, completed_id, interrupted_id))
        self.start()
        code, completed, _ = self.call(f"/api/job/{completed_id}")
        self.assertEqual(code, 200)
        self.assertEqual((completed["state"], completed["result"]["text"]),
                         ("done", "修改稿"))
        code, interrupted, _ = self.call(f"/api/job/{interrupted_id}")
        self.assertEqual((code, interrupted["state"]), (200, "error"))
        self.assertIn("退回", interrupted["error"])
        self.assertEqual(billing.summary(account)["balance"], 798)


if __name__ == "__main__":
    unittest.main()

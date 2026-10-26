"""Durability, isolation, and optimistic-save tests for manuscript/job storage."""
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "web"))
from workspace_store import WorkspaceStore  # noqa: E402


class WorkspaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite3"
        self.store = WorkspaceStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_multiple_manuscripts_survive_restart_and_are_owner_scoped(self):
        value = {"name": "draft.docx", "kind": "docx", "source": "original",
                 "current": "original", "report": {"summary": {"findings": 2}},
                 "notices": [], "document": {"name": "draft.docx", "kind": "docx",
                                             "data": "UEsDBA==", "meta": {}}}
        first = self.store.create_manuscript("account-a", value)
        second = self.store.create_manuscript("account-a", {**value, "name": "second.docx"})
        restarted = WorkspaceStore(self.path)
        self.assertEqual(len(restarted.list_manuscripts("account-a")), 2)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(restarted.get_manuscript("account-a", first["id"])["document"],
                         value["document"])
        self.assertIsNone(restarted.get_manuscript("account-b", first["id"]))

    def test_save_is_revision_guarded(self):
        value = {"name": "paste", "kind": "text", "source": "original",
                 "current": "original", "report": None, "notices": [], "document": None}
        doc = self.store.create_manuscript("a", value)
        status, saved = self.store.update_manuscript(
            "a", doc["id"], 1, {"current": "edited", "report": None, "notices": []})
        self.assertEqual((status, saved["revision"], saved["source"]),
                         ("saved", 2, "original"))
        status, _ = self.store.update_manuscript(
            "a", doc["id"], 1, {"current": "stale", "report": None, "notices": []})
        self.assertEqual(status, "conflict")
        self.assertEqual(self.store.get_manuscript("a", doc["id"])["current"], "edited")
        self.assertEqual([v["revision"] for v in self.store.list_versions("a", doc["id"])], [2, 1])
        self.assertEqual(self.store.get_version("a", doc["id"], 2)["text"], "edited")
        self.assertIsNone(self.store.get_version("b", doc["id"], 2))

    def test_list_counts_non_whitespace_characters_after_edits(self):
        source = "A B\n中\t文😀\u200b"
        doc = self.store.create_manuscript("a", {
            "name": "mixed", "kind": "text", "source": source,
            "current": source, "report": None, "notices": [], "document": None,
        })
        listing = self.store.list_manuscripts("a")
        self.assertEqual((listing[0]["source_chars"], listing[0]["current_chars"]),
                         (5, 5))

        status, _ = self.store.update_manuscript("a", doc["id"], 1, {
            "current": "English 中文, 2026 😀", "report": None, "notices": [],
        })
        self.assertEqual(status, "saved")
        listing = self.store.list_manuscripts("a")
        self.assertEqual((listing[0]["source_chars"], listing[0]["current_chars"]),
                         (5, 15))
        self.assertEqual(self.store.list_manuscripts("b"), [])

    def test_job_result_persists_and_retries_dedupe(self):
        jid = "job_" + "a" * 24
        status, _ = self.store.claim_job("a", "request_123", "hash", jid, 2)
        self.assertEqual(status, "created")
        self.store.update_job(jid, result={"text": "usable", "n_accepted": 1},
                              state="done", phase="complete", billing={"status": "committed"})
        restarted = WorkspaceStore(self.path)
        job = restarted.get_job("a", jid)
        self.assertEqual(job["result"]["text"], "usable")
        self.assertIsNone(restarted.get_job("b", jid))
        self.assertEqual(restarted.claim_job("a", "request_123", "hash", jid, 2)[0], "reused")
        self.assertEqual(restarted.claim_job("a", "request_123", "other", jid, 2)[0], "conflict")

    def test_queued_jobs_survive_restart_and_run_in_order(self):
        first = "job_" + "1" * 24
        second = "job_" + "2" * 24
        for jid in (first, second):
            status, job = self.store.claim_job(
                "a", jid, "hash-" + jid, jid, 1,
                request={"text": "正文", "strength": "conservative"})
            self.assertEqual(status, "created")
            self.assertEqual(job["state"], "queued")
            self.store.update_job(jid, billing={"status": "reserved"})
        restarted = WorkspaceStore(self.path)
        running = restarted.start_next_job(1)
        self.assertEqual(running["id"], first)
        self.assertEqual(running["request"]["text"], "正文")
        self.assertIsNone(restarted.start_next_job(1))
        restarted.update_job(first, state="done")
        self.assertEqual(restarted.start_next_job(1)["id"], second)

    def test_unreserved_queued_claim_can_be_recovered_after_crash(self):
        jid = "job_" + "3" * 24
        self.store.claim_job("a", "request_unreserved", "hash", jid, 2,
                             request={"text": "正文", "strength": "conservative"})
        restarted = WorkspaceStore(self.path)
        self.assertEqual([job["id"] for job in restarted.unreserved_jobs()], [jid])
        self.assertIsNone(restarted.start_next_job(2))
        restarted.update_job(jid, state="error", phase="error")
        self.assertEqual(restarted.unreserved_jobs(), [])
        self.assertIsNone(restarted.get_job("a", jid)["request"])


if __name__ == "__main__":
    unittest.main()

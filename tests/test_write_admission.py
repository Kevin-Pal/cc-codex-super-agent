"""One write-admission rule for direct leases, takeovers and Worker dispatch."""
import hashlib
import json
import subprocess
import time
import unittest
from unittest.mock import patch

import test_takeover

from claude_codex_workflow.store import Store


class WriteAdmissionTests(unittest.TestCase):
    # Borrow the takeover fixture helpers without re-collecting the takeover tests.
    request, start, opened, send, guarded = (test_takeover.TakeoverTests.request, test_takeover.TakeoverTests.start, test_takeover.TakeoverTests.opened,
                                            test_takeover.TakeoverTests.send, test_takeover.TakeoverTests.guarded)

    def setUp(self):
        test_takeover.TakeoverTests.setUp(self)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)

    def direct(self, path, router="router-a", **extra):
        return self.request("direct", router=router, paths=[str(path)], reason="tiny fix", **extra)

    def running(self, router="router-b", cwd=None):
        opened = self.opened(router=router, cwd=cwd)
        task = self.send(opened, router=router)
        self.manager.store.execute("UPDATE tasks SET state='RUNNING' WHERE id=?", (task["task_id"],))
        return opened, task

    def test_admission_direct_rejects_running_writer_in_same_worktree(self):
        first = self.project / "first"
        first.mkdir()
        self.running(cwd=first)
        with self.assertRaisesRegex(ValueError, "cancel|sync"):
            self.direct(self.project / "second" / "x.py")
        self.assertEqual(self.manager.store.rows("SELECT * FROM leases"), [])

    def test_admission_direct_respects_other_router_takeover_but_not_its_own(self):
        self.start(router="router-b")
        with self.assertRaisesRegex(ValueError, "takeover"):
            self.direct(self.project / "x.py")
        self.request("takeover", router="router-b", release=True)
        self.start(router="router-a")
        self.assertEqual(self.direct(self.project / "x.py")["paths"], [str((self.project / "x.py").resolve())])

    def test_admission_other_router_lease_blocks_takeover_and_direct(self):
        self.direct(self.project / "x.py", router="router-b")
        with self.assertRaisesRegex(ValueError, "lease"):
            self.start(router="router-a")
        with self.assertRaisesRegex(ValueError, "lease"):
            self.direct(self.project / "y.py", router="router-a")

    def test_admission_manual_worker_of_any_router_in_same_worktree_blocks(self):
        sub = self.project / "sub"
        sub.mkdir()
        opened = self.opened(router="router-b", cwd=sub)
        self.manager.control(opened["worker"]["id"], "router-b", "manual")
        with self.assertRaisesRegex(ValueError, "manual|human"):
            self.start(router="router-a", scope=[str(self.project / "other")])
        with self.assertRaisesRegex(ValueError, "manual|human"):
            self.direct(self.project / "z.py")

    def test_admission_live_lease_holds_dispatch_then_requires_resync(self):
        opened = self.opened()
        queued = self.send(opened)
        self.direct(self.project / "x.py", seconds=5)
        self.manager._schedule_once()
        self.assertEqual(self.fake.started, [])
        self.assertEqual(self.manager.store.task(queued["task_id"])["state"], "QUEUED")
        with patch("time.time", return_value=time.time() + 10):
            self.manager._schedule_once()
        # The Router changed files under the Worker; the old package must not run blind.
        self.assertEqual(self.manager.store.task(queued["task_id"])["state"], "BLOCKED")
        self.assertEqual(self.fake.started, [])

    def test_admission_direct_work_enters_worker_sync(self):
        opened = self.opened()
        before = opened["sync"]["sync_token"]
        self.direct(self.project / "x.py")
        view = self.manager.sync(opened["worker"]["id"], "router-a")
        self.assertNotEqual(view["sync_token"], before)
        self.assertEqual([e["kind"] for e in view["router_direct_work"]], ["router_direct"])
        self.assertEqual(view["router_direct_work"][0]["label"], "Router direct work")

    def test_admission_expiry_invalidates_baseline_taken_during_direct_write(self):
        opened = self.opened()
        self.direct(self.project / "x.py", seconds=5)
        view = self.manager.sync(opened["worker"]["id"], "router-a")
        self.assertEqual(len(view["active_microtasks"]), 1)
        (self.project / "x.py").write_text("changed after sync\n")
        with patch("time.time", return_value=time.time() + 10):
            with self.assertRaisesRegex(ValueError, "changed|sync"):
                self.manager.send(opened["worker"]["id"], "router-a", "Old baseline", "owner", view["sync_token"])
        self.assertEqual(self.fake.started, [])

    def test_admission_queued_during_direct_write_requires_sync_after_expiry(self):
        opened = self.opened()
        self.direct(self.project / "x.py", seconds=5)
        view = self.manager.sync(opened["worker"]["id"], "router-a")
        with patch("shutil.which", return_value=None):
            queued = self.manager.send(opened["worker"]["id"], "router-a", "Provisional baseline", "owner", view["sync_token"])
        (self.project / "x.py").write_text("changed after queueing\n")
        with patch("time.time", return_value=time.time() + 10):
            self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(queued["task_id"])["state"], "BLOCKED")
        self.assertEqual(self.fake.started, [])

    def test_admission_restart_drain_rejects_new_direct_windows(self):
        self.manager.draining = True
        with self.assertRaisesRegex(ValueError, "restart"):
            self.direct(self.project / "x.py")
        self.assertEqual(self.manager.store.rows("SELECT * FROM leases"), [])

    def test_upgrade_keeps_unrelated_legacy_queue_baseline_valid(self):
        opened = self.opened()
        queued = self.send(opened)
        # Persisted 0.2.2 wire format, independent of the new sync implementation.
        old_view = {"external": [], "knowledge": {"AGENTS.md": hashlib.sha256(b"Shared project facts.\n").hexdigest()},
                    "router_direct_work": []}
        old_token = hashlib.sha256(json.dumps(old_view, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.manager.store.execute("UPDATE tasks SET baseline=? WHERE id=?", (old_token, queued["task_id"]))
        other = self.root / "unrelated"
        other.mkdir()
        self.direct(other / "x.py")
        self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(queued["task_id"])["state"], "RUNNING")

    def test_admission_unrelated_direct_does_not_touch_other_project(self):
        other = self.root / "other"
        other.mkdir()
        (other / "AGENTS.md").write_text("Other.\n")
        opened = self.opened(cwd=other)
        self.direct(self.project / "x.py")
        self.assertEqual(self.manager.sync(opened["worker"]["id"], "router-a")["sync_token"], opened["sync"]["sync_token"])

    def test_admission_independent_review_still_runs_during_lease(self):
        opened = self.opened(permission="independent-review")
        queued = self.send(opened)
        self.direct(self.project / "x.py")
        # Read-only review baseline changed only if it was taken before the lease; resync first.
        view = self.manager.sync(opened["worker"]["id"], "router-a")
        with patch("shutil.which", return_value=None):
            fresh = self.manager.send(opened["worker"]["id"], "router-a", "Review", "owner", view["sync_token"], key="fresh")
        self.manager.cancel(queued["task_id"], "router-a")
        self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(fresh["task_id"])["state"], "RUNNING")

    def test_guard_v2_notebook_edit_is_governed(self):
        data_path = self.project / "analysis.ipynb"
        self.assertIn('"deny"', self.guarded(data_path, tool="NotebookEdit"))
        self.start()
        self.assertEqual(self.guarded(data_path, tool="NotebookEdit"), "")

    def test_guard_v2_docs_directory_counts_only_inside_project(self):
        nested = self.root / "docs" / "app"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(nested)], check=True, capture_output=True)
        self.assertIn('"deny"', self.guarded(nested / "main.py"))
        self.assertEqual(self.guarded(self.project / "docs" / "build.py"), "")
        self.assertEqual(self.guarded(nested / "README.md"), "")

    def test_guard_v2_unreadable_state_denies_code_but_not_prose(self):
        Store(self.root / "state").close()
        with patch("claude_codex_workflow.hooks.Store", side_effect=RuntimeError("database is locked")):
            self.assertIn("unreadable", self.guarded(self.project / "code.py"))
            self.assertEqual(self.guarded(self.project / "notes.md"), "")


if __name__ == "__main__":
    unittest.main()

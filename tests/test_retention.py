import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_codex_workflow.cli import main
from claude_codex_workflow.hooks import context, guard
from claude_codex_workflow.manager import Manager
from claude_codex_workflow.service import dispatch
from claude_codex_workflow.store import Store
from test_workflow import FakeNative


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "AGENTS.md").write_text("Keep approved behavior.\n")
        self.fake = FakeNative()
        self.manager = Manager(self.root / "state", client=self.fake)
        self.addCleanup(self.manager.close)

    def request(self, operation, **params):
        return dispatch(self.manager, {"operation": operation, "params": params})

    def register(self, name, router="router-a", kind="worker", **fields):
        self.manager.store.register(name, kind, router, name, str(self.project), stream=name)
        for key, value in fields.items():
            assert key in {"mode", "pinned", "updated", "active_turn"}
            self.manager.store.execute("UPDATE workers SET " + key + "=? WHERE id=?", (value, name))
        return name

    def open(self):
        self.manager.register_router("router-a", "Design", str(self.project))
        with patch("shutil.which", return_value=None):
            return self.manager.open("router-a", "Design", str(self.project), "UI", stream="ui")

    def cli(self, *args):
        with patch("claude_codex_workflow.cli.call", side_effect=lambda op, p: self.request(op, **p)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = main([*args, "--router", "router-a"])
        return code, json.loads(output.getvalue())

    def test_priority_and_temps_are_filtered_before_limit(self):
        for n in range(12):
            self.register("temp-" + str(n), kind="temp")
        self.register("idle-old", updated=1)
        self.register("idle-new", updated=2)
        self.register("main", pinned=1, updated=1)
        self.register("review")
        task = self.manager.store.enqueue("review", "router-a", "one", "Review", "owner", "model", "effort")
        self.manager.store.finish(task["id"], "READY", "Evidence")
        self.register("active", active_turn="human-turn")
        rows = self.request("list", router="router-a", limit=4)
        self.assertEqual([r["id"] for r in rows], ["active", "review", "main", "idle-new"])
        self.assertEqual([r["activity"] for r in rows], ["busy", "needs_review", "idle", "idle"])

    def test_search_is_literal_scoped_and_does_not_load_native_history(self):
        self.register("exports_%")
        self.register("exports-other")
        self.register("exports-foreign", router="router-b")
        with patch.object(self.fake, "request", side_effect=AssertionError("History must stay unloaded")):
            self.assertEqual([r["id"] for r in self.request("list", router="router-a", query="_%")], ["exports_%"])
            self.assertEqual(len(self.request("list", router="router-a", query="exports")), 2)

    def test_pin_roundtrip_keeps_manual_and_paused_control_and_ownership(self):
        for mode in ["manual", "paused"]:
            tid = self.register(mode, mode=mode)
            code, response = self.cli("control", tid, "--pin")
            self.assertEqual(code, 0)
            self.assertTrue(response["result"]["pinned"])
            self.assertEqual(response["result"]["mode"], mode)
            with self.assertRaisesRegex(ValueError, "Different Router"):
                self.request("control", worker_id=tid, router="other", pinned=False)
            code, response = self.cli("control", tid, "--unpin")
            self.assertEqual(code, 0)
            self.assertFalse(response["result"]["pinned"])
            self.assertEqual(response["result"]["mode"], mode)
        with Store(self.root / "state") as reopened:
            self.assertEqual(reopened.worker("manual")["mode"], "manual")

    def test_cli_control_compatibility_and_invalid_preferences(self):
        self.register("one")
        self.assertEqual(self.cli("control", "one", "paused")[0], 0)
        self.assertEqual(self.cli("control", "one")[0], 1)
        for params in [{"limit": 0}, {"limit": True}, {"query": " "}, {"include_released": "yes"}]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.request("list", router="router-a", **params)
        self.register("temp", kind="temp")
        with self.assertRaisesRegex(ValueError, "Temporary"):
            self.request("control", worker_id="temp", router="router-a", pinned=True)

    def test_release_is_not_deletion_or_automatic_readoption(self):
        self.register("old")
        self.request("control", worker_id="old", router="router-a", mode="released")
        self.assertEqual(self.request("list", router="router-a"), [])
        code, response = self.cli("list", "--all", "--query", "old")
        self.assertEqual(code, 0)
        self.assertEqual(response["result"][0]["mode"], "released")
        self.assertEqual(self.manager.store.worker("old")["id"], "old")
        with self.assertRaisesRegex(ValueError, "released"):
            self.request("control", worker_id="old", router="router-a", pinned=True)

    def test_accepted_worker_remains_reusable_in_same_native_thread(self):
        opened = self.open()
        tid = opened["worker"]["id"]
        with patch("shutil.which", return_value=None):
            task = self.manager.send(tid, "router-a", "Approved UI implementation", "owner", opened["sync"]["sync_token"])
        self.manager._schedule_once()
        self.fake.complete(tid, "UI implemented and checked")
        self.manager.reconcile(self.manager.store.worker(tid))
        self.manager.store.decide(task["task_id"], "router-a", True, "Verified artifact")
        self.assertEqual(self.request("list", router="router-a")[0]["activity"], "idle")
        self.assertEqual(self.open()["worker"]["id"], tid)
        self.assertEqual(len(self.fake.threads), 1)

    def test_hook_uses_bounded_priority_roster_and_full_roster_remains_searchable(self):
        for n in range(12):
            self.register("worker-" + str(n), updated=n + 1)
        self.register("old-main", pinned=1, updated=0)
        self.register("hidden-temp", kind="temp")
        with patch("claude_codex_workflow.hooks.call", side_effect=lambda op, p: self.request(op, **p)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            context({"session_id": "router-a", "cwd": str(self.project)})
        text = json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("old-main=old-main", text)
        self.assertNotIn("worker-0=worker-0", text)
        self.assertNotIn("hidden-temp", text)
        self.assertEqual(len(self.request("list", router="router-a")), 13)
        self.assertEqual(self.cli("list", "--query", "worker-0")[1]["result"][0]["id"], "worker-0")

    def test_explicit_claude_refinement_uses_existing_takeover_without_quota_failure(self):
        opened = self.open()
        ui = self.project / "ui"
        ui.mkdir()
        self.request("takeover", router="router-a", scope=[str(ui)],
                     reason="User explicitly assigned Claude the visual refinement", hours=1)
        def edit(path):
            with patch.dict("os.environ", {"CCW_HOME": str(self.root / "state")}), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                guard({"session_id": "router-a", "cwd": str(self.project), "tool_name": "Edit",
                       "tool_input": {"file_path": str(path)}})
            return output.getvalue()
        self.assertEqual(edit(ui / "page.tsx"), "")
        self.assertIn('"deny"', edit(self.project / "server.py"))
        self.request("takeover", router="router-a", release=True, note="Visual checks recorded")
        self.assertIn('"deny"', edit(ui / "page.tsx"))
        sync = self.manager.sync(opened["worker"]["id"], "router-a")
        self.assertEqual(len(sync["router_direct_work"]), 2)
        self.assertNotEqual(sync["sync_token"], opened["sync"]["sync_token"])
        self.assertEqual(self.manager.store.rows("SELECT * FROM tasks"), [])


class RetentionMigrationTests(unittest.TestCase):
    def test_existing_registry_gains_pin_without_changing_control_or_schema(self):
        with tempfile.TemporaryDirectory() as root:
            with Store(root) as old:
                old.register("prior", "worker", "router", "Existing", root)
                old.execute("UPDATE workers SET mode='paused' WHERE id='prior'")
                old.execute("ALTER TABLE workers DROP COLUMN pinned")
            for _ in range(2):
                with Store(root) as upgraded:
                    row = upgraded.worker("prior")
                    self.assertEqual((row["pinned"], row["mode"]), (0, "paused"))
                    self.assertEqual(upgraded.one("SELECT value FROM meta WHERE key='schema'")["value"], "1")


if __name__ == "__main__":
    unittest.main()

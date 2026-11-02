import contextlib
import io
import json
import os
import subprocess
import tempfile
import threading
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


class TakeoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "AGENTS.md").write_text("Shared project facts.\n")
        self.fake = FakeNative()
        self.manager = Manager(self.root / "state", client=self.fake)
        self.addCleanup(self.manager.close)

    def request(self, operation, **params):
        return dispatch(self.manager, {"operation": operation, "params": params})

    def start(self, router="router-a", scope=None, **extra):
        return self.request("takeover", router=router, scope=scope or [str(self.project)],
                            reason="Codex quota unavailable", **extra)

    def opened(self, router="router-a", cwd=None, **extra):
        with patch("shutil.which", return_value=None):
            return self.manager.open(router, "Project", str(cwd or self.project), "Implementation", stream="work", **extra)

    def send(self, opened, router="router-a", **extra):
        with patch("shutil.which", return_value=None):
            return self.manager.send(opened["worker"]["id"], router, "Approved work", "owner approval",
                                     opened["sync"]["sync_token"], **extra)

    def guarded(self, path, router="router-a", tool="Edit"):
        data = {"session_id": router, "cwd": str(self.project), "tool_name": tool,
                "tool_input": {"file_path": str(path)}}
        with patch.dict(os.environ, {"CCW_HOME": str(self.root / "state")}), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            guard(data)
        return output.getvalue()

    def hook_context(self, router="router-a"):
        with patch("claude_codex_workflow.hooks.call", side_effect=lambda op, p: self.request(op, **p)), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            context({"session_id": router, "cwd": str(self.project)})
        return json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"]

    def test_cli_start_status_release_and_audit_events(self):
        second = self.root / "second.py"
        args = ["takeover", "--router", "router-a", "--scope", str(self.project),
                "--scope", str(second), "--reason", "Quota until evening", "--hours", "8"]
        with patch("claude_codex_workflow.cli.call", side_effect=lambda op, p: self.request(op, **p)):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(args), 0)
            started = json.loads(output.getvalue())["result"]
            self.assertEqual(started["scope"], [str(self.project), str(second)])
            self.assertEqual(started["expires"] - started["created"], 8 * 3600)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["takeover", "--router", "router-a", "--status"]), 0)
            self.assertEqual(len(json.loads(output.getvalue())["result"]["takeovers"]), 1)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["takeover", "--router", "router-a", "--release", "--note", "Checks in shared docs"]), 0)
            self.assertEqual(len(json.loads(output.getvalue())["result"]["released"]), 1)
        self.assertEqual(self.request("takeover", router="router-a", status=True)["takeovers"], [])
        events = self.request("events", router="router-a")
        self.assertEqual([e["kind"] for e in events], ["takeover_started", "takeover_released"])
        for event in events:
            payload = json.loads(event["payload"])
            self.assertEqual(payload["scope"], [str(self.project), str(second)])
            self.assertEqual(payload["reason"], "Quota until evening")
            self.assertEqual(payload["expires"], started["expires"])
            self.assertIn("note", payload)
        self.assertEqual(json.loads(events[-1]["payload"])["note"], "Checks in shared docs")
        self.request("takeover", router="router-a", release=True)
        self.assertEqual(len(self.request("events", router="router-a")), 2)
        self.assertEqual(self.request("events", router="other-router"), [])
        self.assertEqual(self.manager.store.rows("SELECT * FROM tasks"), [])

    def test_reason_scope_and_duration_are_validated(self):
        for params in [{"scope": [str(self.project)]}, {"scope": [str(self.project)], "reason": " "},
                       {"scope": [], "reason": "quota"}, {"scope": [""], "reason": "quota"},
                       {"status": True, "scope": [str(self.project)], "reason": "quota"}]:
            with self.subTest(params=params), self.assertRaisesRegex(ValueError, "scope|reason|mode"):
                self.request("takeover", router="router-a", **params)
        for hours in [0, -1, 8.01, float("nan"), float("inf")]:
            with self.subTest(hours=hours), self.assertRaisesRegex(ValueError, "hours"):
                self.start(hours=hours)
        self.assertEqual(self.manager.store.rows("SELECT * FROM events WHERE kind='takeover_started'"), [])

    def test_note_is_only_accepted_when_releasing(self):
        for params in [{"scope": [str(self.project)], "reason": "quota", "note": "misplaced note"},
                       {"status": True, "note": "misplaced note"}]:
            with self.subTest(params=params), self.assertRaisesRegex(ValueError, "note.*release"):
                self.request("takeover", router="router-a", **params)

    def test_guard_allows_only_owned_scopes_with_component_and_symlink_boundaries(self):
        source = self.project / "src"
        source.mkdir()
        sibling = self.project / "src-other"
        sibling.mkdir()
        (source / "escape").symlink_to(sibling, target_is_directory=True)
        exact_file = self.project / "one.py"
        self.start(scope=[str(source), str(exact_file)])
        for tool in ["Write", "Edit", "MultiEdit"]:
            with self.subTest(tool=tool):
                self.assertEqual(self.guarded("src/new/deep.py", tool=tool), "")
                self.assertEqual(self.guarded(exact_file, tool=tool), "")
        for path in [sibling / "code.py", source / "escape/code.py", self.project / "one.py.other"]:
            with self.subTest(path=path):
                self.assertIn('"deny"', self.guarded(path))
        self.assertIn('"deny"', self.guarded(source / "code.py", router="router-b"))

    def test_expiration_revokes_guard_and_context_and_records_one_end_event(self):
        lease = self.start()
        self.assertEqual(lease["expires"] - lease["created"], 2 * 3600)
        text = self.hook_context()
        self.assertIn("takeover", text.lower())
        self.assertIn(str(self.project), text)
        self.assertIn("共享项目文档", text)
        self.assertIn("独立复核", text)
        with patch("time.time", return_value=lease["expires"]):
            self.assertIn('"deny"', self.guarded(self.project / "code.py"))
            self.assertNotIn("Active takeover:", self.hook_context())
            self.assertEqual(self.request("takeover", router="router-a", status=True)["takeovers"], [])
        ends = self.manager.store.rows("SELECT * FROM events WHERE kind='takeover_released'")
        self.assertEqual(len(ends), 1)
        self.assertEqual(json.loads(ends[0]["payload"])["note"], "expired")

    def test_release_revokes_only_takeover_and_preserves_exact_file_microtask(self):
        path = self.project / "micro.py"
        self.request("direct", router="router-a", paths=[str(path)], reason="one tiny change")
        self.start()
        self.request("takeover", router="router-a", release=True)
        self.assertEqual(self.guarded(path), "")
        self.assertIn('"deny"', self.guarded(self.project / "other.py"))

    def test_running_and_dispatching_writers_of_any_router_block_takeover(self):
        opened = self.opened(router="router-b")
        task = self.send(opened, router="router-b")
        for state in ["RUNNING", "DISPATCHING"]:
            self.manager.store.execute("UPDATE tasks SET state=? WHERE id=?", (state, task["task_id"]))
            with self.subTest(state=state), self.assertRaisesRegex(ValueError, "cancel|sync"):
                self.start(scope=[str(self.project / "new.py")])
        self.assertEqual(self.manager.store.rows("SELECT * FROM events WHERE kind='takeover_started'"), [])

    def test_writer_in_sibling_directory_of_same_git_worktree_blocks_takeover(self):
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        first, second = self.project / "first", self.project / "second"
        first.mkdir()
        second.mkdir()
        opened = self.opened(router="router-b", cwd=first)
        task = self.send(opened, router="router-b")
        self.manager.store.execute("UPDATE tasks SET state='RUNNING' WHERE id=?", (task["task_id"],))
        with self.assertRaisesRegex(ValueError, "cancel|sync"):
            self.start(scope=[str(second)])

    def test_owned_manual_worker_requires_human_confirmation(self):
        opened = self.opened()
        self.manager.control(opened["worker"]["id"], "router-a", "manual")
        with self.assertRaisesRegex(ValueError, "manual|human"):
            self.start()
        self.assertEqual(self.manager.store.worker(opened["worker"]["id"])["mode"], "manual")

    def test_independent_review_does_not_block_takeover(self):
        opened = self.opened(permission="independent-review")
        task = self.send(opened)
        self.manager._dispatch(self.manager.store.task(task["task_id"]))
        self.start()
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "RUNNING")

    def test_independent_review_can_be_dispatched_during_takeover(self):
        self.start()
        opened = self.opened(permission="independent-review")
        task = self.send(opened)
        self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "RUNNING")

    def test_takeover_grant_is_serialized_with_scheduler_dispatch(self):
        opened = self.opened()
        task = self.send(opened)
        checked, proceed, scheduled = threading.Event(), threading.Event(), threading.Event()
        attempted = threading.Event()
        original = self.manager.store.start_takeover
        errors = []

        def delayed_grant(*args):
            checked.set()
            if not proceed.wait(3):
                raise RuntimeError("Timed out waiting to record takeover")
            return original(*args)

        def grant():
            try:
                self.start()
            except Exception as error:
                errors.append(error)

        def schedule():
            attempted.set()
            try:
                self.manager._schedule_once()
            except Exception as error:
                errors.append(error)
            finally:
                scheduled.set()

        with patch.object(self.manager.store, "start_takeover", side_effect=delayed_grant):
            writer = threading.Thread(target=grant)
            scheduler = threading.Thread(target=schedule)
            writer.start()
            try:
                self.assertTrue(checked.wait(2))
                scheduler.start()
                self.assertTrue(attempted.wait(2))
                self.assertFalse(scheduled.wait(.05))
            finally:
                proceed.set()
                writer.join(3)
                if scheduler.ident is not None:
                    scheduler.join(3)
        self.assertFalse(writer.is_alive())
        self.assertFalse(scheduler.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.fake.started, [])
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "QUEUED")

    def test_active_takeover_blocks_new_and_queued_writers_then_requires_resync(self):
        opened = self.opened()
        queued = self.send(opened)
        self.start()
        with self.assertRaisesRegex(ValueError, "takeover"):
            self.send(opened, key="new-work")
        self.manager._schedule_once()
        self.assertEqual(self.fake.started, [])
        self.assertEqual(self.manager.store.task(queued["task_id"])["state"], "QUEUED")
        self.request("takeover", router="router-a", release=True, note="Changes checked")
        self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(queued["task_id"])["state"], "BLOCKED")
        self.assertEqual(self.fake.started, [])

    def test_overlapping_takeovers_of_different_routers_are_rejected(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "takeover"):
            self.start(router="router-b")
        self.assertEqual(self.request("takeover", router="router-b", status=True)["takeovers"], [])

    def test_sync_and_worker_prompt_expose_direct_work_without_forging_turns(self):
        opened = self.opened()
        thread = opened["worker"]["id"]
        self.start()
        self.request("takeover", router="router-a", release=True, note="Evidence in shared docs")
        view = self.manager.sync(thread, "router-a")
        self.assertNotEqual(view["sync_token"], opened["sync"]["sync_token"])
        self.assertEqual([e["kind"] for e in view["router_direct_work"]], ["takeover_started", "takeover_released"])
        self.assertTrue(all(e["label"] == "Router direct work" for e in view["router_direct_work"]))
        self.assertEqual(view["recent_turns"], [])
        self.assertEqual(self.fake.started, [])
        with self.assertRaisesRegex(ValueError, "sync"):
            self.send(opened)
        opened["sync"] = view
        task = self.send(opened)
        self.manager._dispatch(self.manager.store.task(task["task_id"]))
        prompt = self.fake.started[0][1]["input"][0]["text"]
        for text in ["Router direct work", "Codex quota unavailable", "Evidence in shared docs"]:
            self.assertIn(text, prompt)
        self.assertEqual(self.manager.sync(thread, "router-a")["router_direct_work"], [])
        self.assertEqual(len(self.manager.sync(thread, "router-a", history=True)["router_direct_work"]), 2)
        self.assertEqual(self.manager.store.rows("SELECT * FROM events WHERE kind='review'"), [])

    def test_unrelated_takeover_does_not_change_worker_sync_token(self):
        opened = self.opened()
        other = self.root / "other"
        other.mkdir()
        self.start(router="router-b", scope=[str(other)])
        view = self.manager.sync(opened["worker"]["id"], "router-a")
        self.assertEqual(view["router_direct_work"], [])
        self.assertEqual(view["sync_token"], opened["sync"]["sync_token"])


class TakeoverMigrationTests(unittest.TestCase):
    def test_schema_one_upgrade_preserves_workers_tasks_leases_and_events(self):
        with tempfile.TemporaryDirectory() as temp:
            with Store(temp) as old:
                # Remove the additive V2 table to reproduce the complete legacy schema.
                old.execute("DROP TABLE IF EXISTS takeovers")
                old.execute("UPDATE meta SET value='1' WHERE key='schema'")
                old.execute("INSERT INTO routers VALUES(?,?,?,?)", ("router-a", "Existing Router", temp, 1))
                old.execute("INSERT INTO meta VALUES('view:legacy-thread','{}')")
                old.register("legacy-thread", "worker", "router-a", "Existing Worker", temp)
                task = old.enqueue("legacy-thread", "router-a", "key", "Preserve work", "owner", "model", "effort")
                old.execute("INSERT INTO leases VALUES(?,?,?,?)", ("router-a", str(Path(temp) / "one.py"), time.time() + 600, "microtask"))
                before = old.rows("SELECT * FROM events")
            for _ in range(2):
                with Store(temp) as upgraded:
                    self.assertEqual(upgraded.one("SELECT value FROM meta WHERE key='schema'")["value"], "1")
                    self.assertEqual(upgraded.worker("legacy-thread")["name"], "Existing Worker")
                    self.assertEqual(upgraded.one("SELECT name FROM routers")["name"], "Existing Router")
                    self.assertEqual(upgraded.one("SELECT value FROM meta WHERE key='view:legacy-thread'")["value"], "{}")
                    self.assertEqual(upgraded.task(task["id"])["prompt"], "Preserve work")
                    self.assertEqual(upgraded.task(task["id"])["state"], "QUEUED")
                    self.assertEqual(upgraded.one("SELECT reason FROM leases")["reason"], "microtask")
                    self.assertEqual(upgraded.rows("SELECT * FROM events"), before)
                    self.assertEqual(upgraded.rows("SELECT * FROM takeovers"), [])

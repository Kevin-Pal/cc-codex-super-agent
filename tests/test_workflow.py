import contextlib
import io
import json
import os
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_codex_workflow.cli import main
from claude_codex_workflow.install import install, snapshot, uninstall
from claude_codex_workflow.manager import Manager, worker_name
from claude_codex_workflow.store import Store
from claude_codex_workflow.hooks import context, guard, watch
from claude_codex_workflow.service import dispatch


class FakeNative:
    closed = False
    server_info = {"userAgent": "test"}
    def __init__(self):
        self.threads = {}
        self.started = []

    def close(self):
        self.closed = True

    def request(self, method, params):
        if method == "model/list":
            return {"data": [{"id": m, "model": m, "supportedReasoningEfforts": [{"reasoningEffort": e} for e in ["max", "xhigh"]]} for m in ["gpt-6-sol", "gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra"]]}
        if method == "thread/start":
            tid = "thread-" + str(len(self.threads))
            thread = {"id": tid, "cwd": params["cwd"], "ephemeral": params["ephemeral"], "name": "", "status": {"type": "idle"}, "turns": []}
            self.threads[tid] = thread
            return {"thread": thread}
        thread = self.threads[params["threadId"]]
        if method == "thread/name/set":
            thread["name"] = params["name"]
            return {}
        if method in ["thread/read", "thread/resume"]:
            return {"thread": thread}
        if method == "thread/turns/list":
            return {"data": list(reversed(thread["turns"]))}
        if method == "turn/start":
            if thread["status"]["type"] == "active":
                raise ValueError("active turn conflict")
            turn = {"id": "turn-" + str(len(self.started)), "status": "inProgress", "items": []}
            self.started.append((thread["id"], params))
            thread["turns"].append(turn)
            thread["status"] = {"type": "active"}
            return {"turn": turn}
        if method == "thread/unsubscribe":
            return {}
        if method == "turn/interrupt":
            turn = next(t for t in thread["turns"] if t["id"] == params["turnId"])
            turn["status"] = "interrupted"
            thread["status"] = {"type": "idle"}
            return {}
        raise ValueError(method)

    def complete(self, tid, text="observed result"):
        thread = self.threads[tid]
        thread["turns"][-1].update(status="completed", items=[{"type": "agentMessage", "text": text}])
        thread["status"] = {"type": "idle"}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "AGENTS.md").write_text("Keep the export fields stable.\n")
        self.fake = FakeNative()
        self.manager = Manager(self.root / "state", client=self.fake)

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def opened(self, **extra):
        with patch("shutil.which", return_value=None):
            return self.manager.open("router-a", "Data platform", str(self.project), "Exports", stream="export", **extra)

    def send(self, opened, **extra):
        with patch("shutil.which", return_value=None):
            return self.manager.send(opened["worker"]["id"], "router-a", "Implement the approved outcome", "test owner authorization", opened["sync"]["sync_token"], **extra)

    def test_reuse_identity_and_idempotency(self):
        a = self.opened()
        self.assertEqual(a["worker"]["id"], self.opened()["worker"]["id"])
        one = self.send(a)
        two = self.send(a)
        self.assertEqual(one["task_id"], two["task_id"])
        self.manager._dispatch(self.manager.store.task(one["task_id"]))
        self.assertEqual(len(self.fake.started), 1)
        self.assertEqual(self.fake.started[0][1]["model"], "gpt-6.1-sol")
        self.assertEqual(self.fake.started[0][1]["effort"], "xhigh")

    def test_shared_file_change_requires_resync(self):
        a = self.opened()
        (self.project / "AGENTS.md").write_text("Preserve a newly authorized field.\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.send(a)

    def test_sync_only_replays_new_material_after_ack(self):
        a = self.opened();tid = a["worker"]["id"]
        self.fake.threads[tid]["turns"].append({"id": "external-old", "status": "completed", "items": [{"type": "userMessage", "content": [{"type": "text", "text": "A confirmed requirement"}]}]})
        a["sync"] = self.manager.sync(tid, "router-a")
        self.assertTrue(a["sync"]["recent_turns"])
        self.send(a)
        self.assertEqual(self.manager.sync(tid, "router-a")["recent_turns"], [])
        self.assertTrue(self.manager.sync(tid, "router-a", history=True)["recent_turns"])

    def test_changed_queued_task_does_not_execute(self):
        a = self.opened()
        t = self.send(a)
        (self.project / "AGENTS.md").write_text("A different approved interface\n")
        self.manager._dispatch(self.manager.store.task(t["task_id"]))
        self.assertEqual(self.manager.store.task(t["task_id"])["state"], "BLOCKED")
        self.assertEqual(self.fake.started, [])

    def test_external_input_updates_token_and_preserves_human_name(self):
        a = self.opened()
        tid = a["worker"]["id"]
        self.fake.threads[tid]["turns"].append({"id": "human-1", "status": "completed", "items": [{"type": "userMessage", "content": [{"type": "text", "text": "Keep the old format"}]}]})
        self.fake.threads[tid]["name"] = "Human chosen title"
        self.manager.reconcile(self.manager.store.worker(tid))
        self.assertEqual(self.manager.store.worker(tid)["mode"], "external")
        with self.assertRaises(ValueError):
            self.send(a)
        sync = self.manager.sync(tid, "router-a")
        self.assertIn("Keep the old format", json.dumps(sync))
        self.assertEqual(self.manager.store.worker(tid)["name"], "Human chosen title")
        a["sync"] = sync
        self.send(a)
        self.manager.reconcile(self.manager.store.worker(tid))
        self.assertEqual(self.manager.store.worker(tid)["mode"], "automatic")

    def test_ready_is_not_accepted_and_empty_is_not_success(self):
        a = self.opened()
        t = self.send(a)
        self.manager._dispatch(self.manager.store.task(t["task_id"]))
        self.fake.complete(a["worker"]["id"])
        self.manager.reconcile(self.manager.store.worker(a["worker"]["id"]))
        self.assertEqual(self.manager.store.task(t["task_id"])["state"], "READY")
        self.manager.store.decide(t["task_id"], "router-a", True, "observed result checked")
        self.assertEqual(self.manager.store.task(t["task_id"])["state"], "ACCEPTED")

    def test_pause_survives_completion(self):
        a = self.opened()
        tid = a["worker"]["id"]
        t = self.send(a)
        self.manager._dispatch(self.manager.store.task(t["task_id"]))
        self.manager.control(tid, "router-a", "paused")
        self.fake.complete(tid)
        self.manager.reconcile(self.manager.store.worker(tid))
        self.assertEqual(self.manager.store.worker(tid)["mode"], "paused")
        with self.assertRaisesRegex(ValueError, "paused"):
            self.send(a)

    def test_one_writer_per_worktree(self):
        first = self.opened()
        with patch("shutil.which", return_value=None):
            second = self.manager.open("router-a", "Data platform", str(self.project), "Ingest", stream="ingest")
        one, two = self.send(first), self.send(second)
        self.manager._dispatch(self.manager.store.task(one["task_id"]))
        self.manager._dispatch(self.manager.store.task(two["task_id"]))
        self.assertEqual(len(self.fake.started), 1)
        self.assertEqual(self.manager.store.task(two["task_id"])["state"], "QUEUED")

    def test_blocked_worktree_queue_does_not_starve_other_projects(self):
        first = self.opened()
        with patch("shutil.which", return_value=None):
            second = self.manager.open("router-a", "Data platform", str(self.project), "Ingest", stream="ingest")
            third = self.manager.open("router-a", "Data platform", str(self.project), "Audit", stream="audit")
        other = self.root / "other"; other.mkdir(); (other / "AGENTS.md").write_text("Other project.\n")
        with patch("shutil.which", return_value=None):
            foreign = self.manager.open("router-b", "Other", str(other), "Docs", stream="docs")
        running = self.send(first)
        self.manager._dispatch(self.manager.store.task(running["task_id"]))
        waiting = [self.send(second), self.send(third)]
        with patch("shutil.which", return_value=None):
            late = self.manager.send(foreign["worker"]["id"], "router-b", "Unrelated work", "test owner authorization", foreign["sync"]["sync_token"])
        self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(late["task_id"])["state"], "RUNNING")
        for task in waiting:
            self.assertEqual(self.manager.store.task(task["task_id"])["state"], "QUEUED")

    def test_cancel_during_dispatch_is_not_lost(self):
        opened = self.opened();task = self.send(opened)
        entered, release = threading.Event(), threading.Event()
        original = self.fake.request
        def delayed(method, params):
            if method == "turn/start":
                entered.set();release.wait(3)
            return original(method, params)
        self.fake.request = delayed
        def execute():
            with self.manager.lock:
                self.manager._dispatch(self.manager.store.task(task["task_id"]))
        one = threading.Thread(target=execute);one.start();self.assertTrue(entered.wait(2))
        two = threading.Thread(target=lambda: dispatch(self.manager, {"operation": "cancel", "params": {"task_id": task["task_id"], "router": "router-a"}}))
        two.start();release.set();one.join(3);two.join(3)
        self.assertFalse(one.is_alive() or two.is_alive())
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "CANCELLED")
        self.assertEqual(self.fake.threads[opened["worker"]["id"]]["status"]["type"], "idle")

    def test_empty_completed_turn_is_inconclusive(self):
        a = self.opened()
        task = self.send(a)
        self.manager._dispatch(self.manager.store.task(task["task_id"]))
        self.fake.complete(a["worker"]["id"], "")
        self.manager.reconcile(self.manager.store.worker(a["worker"]["id"]))
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "INCONCLUSIVE")

    def test_result_prefers_final_delivery_over_progress(self):
        a = self.opened();task = self.send(a)
        self.manager._dispatch(self.manager.store.task(task["task_id"]))
        self.fake.complete(a["worker"]["id"])
        self.fake.threads[a["worker"]["id"]]["turns"][-1]["items"] = [
            {"type": "agentMessage", "phase": "commentary", "text": "intermediate progress"},
            {"type": "agentMessage", "phase": "final_answer", "text": "verified deliverable"}]
        self.manager.reconcile(self.manager.store.worker(a["worker"]["id"]))
        self.assertEqual(self.manager.store.task(task["task_id"])["result"], "verified deliverable")

    def test_unknown_dispatch_is_not_replayed_on_recovery(self):
        a = self.opened()
        t = self.send(a)
        self.manager.store.execute("UPDATE tasks SET state='DISPATCHING' WHERE id=?", (t["task_id"],))
        self.manager.recover()
        self.assertEqual(self.manager.store.task(t["task_id"])["state"], "INCONCLUSIVE")
        self.assertEqual(self.fake.started, [])

    def test_takeover_cannot_steal_pending_work(self):
        a = self.opened()
        self.send(a)
        with self.assertRaisesRegex(ValueError, "pending"):
            self.manager.adopt(a["worker"]["id"], "router-b", "Other", from_router="router-a")

    def test_temporary_result_uses_events_and_releases(self):
        a = self.opened(kind="temp")
        t = self.send(a)
        self.manager._dispatch(self.manager.store.task(t["task_id"]))
        tid = a["worker"]["id"]
        turn = self.manager.store.task(t["task_id"])["turn"]
        self.fake.complete(tid, "batch evidence")
        self.manager.on_event({"method": "item/completed", "params": {"threadId": tid, "turnId": turn, "item": {"type": "agentMessage", "text": "batch evidence"}}})
        self.manager.on_event({"method": "turn/completed", "params": {"threadId": tid, "turn": {"id": turn, "status": "completed"}}})
        self.manager.reconcile(self.manager.store.worker(tid))
        self.assertEqual(self.manager.store.task(t["task_id"])["result"], "batch evidence")
        self.assertEqual(self.manager.store.worker(tid)["mode"], "released")
        with patch.dict(os.environ, {"CCW_HOME": str(self.root / "state"), "CCW_WATCH_SECONDS": "0"}), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(watch({"session_id": "router-a"}), 2)

    def test_wakeup_once_and_pause_suppresses_it(self):
        a = self.opened()
        t = self.send(a)
        self.manager.store.finish(t["task_id"], "READY", "done")
        with patch.dict(os.environ, {"CCW_HOME": str(self.root / "state"), "CCW_WATCH_SECONDS": "0"}), contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(watch({"session_id": "router-a"}), 2)
            self.assertIn(t["task_id"], output.getvalue())
            self.assertEqual(watch({"session_id": "router-a"}), 0)

    def test_guard_has_explicit_microtask_exception(self):
        path = self.project / "code.py"
        data = {"session_id": "router-a", "cwd": str(self.project), "tool_name": "Edit", "tool_input": {"file_path": str(path)}}
        with patch.dict(os.environ, {"CCW_HOME": str(self.root / "state")}), contextlib.redirect_stdout(io.StringIO()) as output:
            guard(data)
            self.assertIn('"deny"', output.getvalue())
        dispatch(self.manager, {"operation": "direct", "params": {"router": "router-a", "paths": [str(path)], "seconds": 30, "reason": "one reversible fix"}})
        with patch.dict(os.environ, {"CCW_HOME": str(self.root / "state")}), contextlib.redirect_stdout(io.StringIO()) as output:
            guard(data)
            self.assertEqual(output.getvalue(), "")

    def test_cli_router_identity_fallback_and_explicit_overrides(self):
        cases = [
            ({"CLAUDE_CODE_SESSION_ID": "native-router"}, [], "native-router", "Router"),
            ({"CCW_ROUTER_ID": "", "CLAUDE_CODE_SESSION_ID": "native-router"}, [], "native-router", "Router"),
            ({"CCW_ROUTER_ID": "ccw-router", "CLAUDE_CODE_SESSION_ID": "native-router",
              "CCW_ROUTER_NAME": "Named Router"}, [], "ccw-router", "Named Router"),
            ({"CCW_ROUTER_ID": "ccw-router", "CLAUDE_CODE_SESSION_ID": "native-router",
              "CCW_ROUTER_NAME": "Named Router"},
             ["--router", "explicit-router", "--router-name", "Explicit Router"], "explicit-router", "Explicit Router"),
            ({"CCW_ROUTER_ID": "ccw-router", "CCW_ROUTER_NAME": ""}, [], "ccw-router", "Router"),
            ({"CCW_ROUTER_ID": "ccw-router"}, [], "ccw-router", "Router"),
            ({}, ["--router", "explicit-only"], "explicit-only", "Router"),
        ]
        for env, flags, router, name in cases:
            with self.subTest(env=env, flags=flags), patch.dict(os.environ, env, clear=True), \
                    patch("claude_codex_workflow.cli.call", side_effect=lambda op, p: dispatch(self.manager, {"operation": op, "params": p})), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["router", "--cwd", str(self.project), *flags]), 0, output.getvalue())
                self.assertEqual(json.loads(output.getvalue())["result"],
                                 {"router": router, "name": name, "cwd": str(self.project)})
                registered = self.manager.store.one("SELECT * FROM routers WHERE id=?", (router,))
                self.assertEqual((registered["name"], registered["cwd"]), (name, str(self.project)))

    def test_cli_rejects_missing_router_identity_before_contacting_coordinator(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("claude_codex_workflow.cli.call", side_effect=AssertionError("Unexpected coordinator call")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["list"]), 1)
        self.assertIn("Router ID missing", json.loads(output.getvalue())["error"])

    def test_context_registers_preexisting_session_idempotently_without_env_file(self):
        env_file = self.root / "session.env"
        data = {"session_id": "router-a", "cwd": str(self.project)}
        with patch.dict(os.environ, {"CLAUDE_ENV_FILE": str(env_file)}), \
                patch("claude_codex_workflow.hooks.call", side_effect=lambda op, p: dispatch(self.manager, {"operation": op, "params": p})):
            for _ in range(2):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(context(data), 0)
                hook = json.loads(output.getvalue())["hookSpecificOutput"]
                self.assertEqual(hook["hookEventName"], "UserPromptSubmit")
                self.assertIn("stable ID router-a", hook["additionalContext"])
                rows = self.manager.store.rows("SELECT * FROM routers")
                self.assertEqual(len(rows), 1)
                self.assertEqual((rows[0]["id"], rows[0]["name"], rows[0]["cwd"]),
                                 ("router-a", "project", str(self.project)))
        self.assertFalse(env_file.exists())

    def test_context_refreshes_router_metadata_and_preserves_env_and_workers(self):
        opened = self.opened()
        changed_cwd = self.root / "other-project"
        changed_cwd.mkdir()
        transcript = self.root / "transcript.jsonl"
        transcript.write_text(json.dumps({"type": "custom-title", "customTitle": "Renamed Router"}) + "\n")
        env_file = self.root / "session.env"
        env_file.write_text("preserve existing environment\n")
        data = {"session_id": "router-a", "cwd": str(changed_cwd), "transcript_path": str(transcript)}
        with patch.dict(os.environ, {"CLAUDE_ENV_FILE": str(env_file)}), \
                patch("claude_codex_workflow.hooks.call", side_effect=lambda op, p: dispatch(self.manager, {"operation": op, "params": p})), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(context(data), 0)
        rows = self.manager.store.rows("SELECT * FROM routers")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["id"], rows[0]["name"], rows[0]["cwd"]),
                         ("router-a", "Renamed Router", str(changed_cwd)))
        self.assertIn(opened["worker"]["id"], json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(env_file.read_text(), "preserve existing environment\n")

    def test_start_still_registers_router_and_exports_environment(self):
        transcript = self.root / "transcript.jsonl"
        transcript.write_text(json.dumps({"type": "custom-title", "customTitle": "Data platform"}) + "\n")
        env_file = self.root / "session.env"
        data = {"session_id": "router-a", "cwd": str(self.project), "transcript_path": str(transcript)}
        with patch.dict(os.environ, {"CLAUDE_ENV_FILE": str(env_file)}), \
                patch("claude_codex_workflow.hooks.call", side_effect=lambda op, p: dispatch(self.manager, {"operation": op, "params": p})), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(context(data, start=True), 0)
        self.assertEqual(json.loads(output.getvalue())["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertEqual(self.manager.store.one("SELECT name FROM routers WHERE id='router-a'")["name"], "Data platform")
        self.assertEqual(env_file.read_text(), "\nexport CCW_ROUTER_ID=router-a\nexport CCW_ROUTER_NAME='Data platform'\n")


class InstallTests(unittest.TestCase):
    def test_router_only_rollback_never_restores_unowned_codex_file(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            for rel in [".agents/global", ".local/bin", ".codex"]:(home/rel).mkdir(parents=True,exist_ok=True)
            (home/".agents/global/shared.md").write_text("shared")
            (home/".agents/global/codex.md").write_text("worker")
            (home/".local/bin/agents-sync").write_text("unused for Router-only install")
            target=home/".codex/AGENTS.md";target.write_text("existing")
            install(home,"router",True)
            target.write_text("later independent worker change")
            uninstall(home,True)
            self.assertEqual(target.read_text(),"later independent worker change")
    def test_mixed_hook_row_keeps_unrelated_hook(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp);(home / ".claude").mkdir()
            path = home / ".claude/settings.json"
            other = {"type": "command", "command": "keep-this"}
            path.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "ai-work hook watch"}, other]}]}}))
            install(home, "router", True)
            self.assertEqual(json.loads(path.read_text())["hooks"]["Stop"][0]["hooks"], [other])

    def test_install_is_idempotent_preserves_settings_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / ".claude").mkdir()
            path = home / ".claude/settings.json"
            original = {"idleCompaction": True, "env": {"DISABLE_TELEMETRY": "1"}, "model": "preserve-me", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "existing-hook"}]}]}}
            path.write_text(json.dumps(original));path.chmod(0o600)
            before = snapshot(path)
            one = install(home, "both", True)
            current = json.loads(path.read_text())
            for k in ["idleCompaction", "env", "model"]:
                self.assertEqual(current[k], original[k])
            self.assertEqual(current["hooks"]["Stop"][0], original["hooks"]["Stop"][0])
            self.assertTrue(install(home, "both", True)["unchanged"])
            uninstall(home, True)
            self.assertEqual(snapshot(path), before)
            self.assertFalse((home / ".local/bin/ai-work").exists())

    def test_later_edits_block_rollback(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            install(home, "both", True)
            path = home / ".claude/settings.json"
            data = json.loads(path.read_text());data["user_later_change"] = True;path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "changed later"):
                uninstall(home, True)
            self.assertTrue(json.loads(path.read_text())["user_later_change"])


if __name__ == "__main__":
    unittest.main()

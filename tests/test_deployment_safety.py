import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_codex_workflow import paths, service
from claude_codex_workflow.cli import main
from claude_codex_workflow.install import install
from claude_codex_workflow.manager import Manager
from claude_codex_workflow.store import Store
from test_workflow import FakeNative


class LifecycleSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.fake = FakeNative()
        self.manager = Manager(self.root / "state", client=self.fake)
        self.addCleanup(self.manager.close)
        self.shutdown = []
        self.manager.shutdown = lambda: self.shutdown.append(True)

    def opened(self, kind="worker", stream="one", router="router-a"):
        self.manager.register_router(router, "Project", str(self.project))
        with patch("shutil.which", return_value=None):
            return self.manager.open(router, "Project", str(self.project), stream, stream=stream, kind=kind)

    def send(self, worker, minutes=45, **extra):
        with patch("shutil.which", return_value=None):
            return self.manager.send(worker["worker"]["id"], worker["worker"]["router"], "Approved task", "owner",
                                     worker["sync"]["sync_token"], minutes=minutes, **extra)

    def request(self, operation, **params):
        return service.dispatch(self.manager, {"operation": operation, "params": params})

    def test_run_budget_starts_after_eight_minutes_of_queueing(self):
        with patch("time.time", return_value=1000):
            worker = self.opened()
            task = self.send(worker)
        with patch("time.time", return_value=1480):
            self.manager._schedule_once()
        row = self.manager.store.task(task["task_id"])
        self.assertEqual(row["state"], "RUNNING")
        self.assertEqual(row["started"], 1480)
        self.assertEqual(row["deadline"], 4180)

    def test_queue_budget_is_separate_from_execution_budget(self):
        with patch("time.time", return_value=1000):
            worker = self.opened()
            task = self.send(worker, minutes=1, queue_minutes=10)
        with patch("time.time", return_value=1120):
            self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "RUNNING")
        self.assertEqual(self.manager.store.task(task["task_id"])["deadline"], 1180)

    def test_queue_timeout_never_starts_a_native_turn(self):
        with patch("time.time", return_value=1000):
            worker = self.opened()
            task = self.send(worker, queue_minutes=1)
        with patch("time.time", return_value=1061):
            self.manager._schedule_once()
        row = self.manager.store.task(task["task_id"])
        self.assertEqual(row["state"], "BLOCKED")
        self.assertIn("Queue", row["error"])
        self.assertEqual(self.fake.started, [])

    def test_timed_out_temp_remains_writer_and_idle_restart_blocker_until_completion(self):
        with patch("time.time", return_value=1000):
            worker = self.opened(kind="temp")
            task = self.send(worker, minutes=1)
            self.manager._schedule_once()
            later = self.send(self.opened(stream="two", router="router-b"))
        with patch("time.time", return_value=1061):
            self.manager._schedule_once()
            self.assertEqual(self.manager.store.task(task["task_id"])["state"], "BLOCKED")
            self.assertEqual(self.manager.store.task(later["task_id"])["state"], "QUEUED")
            with self.assertRaisesRegex(ValueError, "idle|temporary|native"):
                self.request("shutdown_when_idle", timeout=0)
            with self.assertRaisesRegex(ValueError, "writer|cancel|sync"):
                self.manager.takeover("router-a", scope=[str(self.project)], reason="quota")
        self.assertEqual(self.shutdown, [])
        self.fake.complete(worker["worker"]["id"], "late verified result")
        self.manager.on_event({"method": "item/completed", "params": {"threadId": worker["worker"]["id"], "turnId": self.manager.store.task(task["task_id"])["turn"], "item": {"type": "agentMessage", "text": "late verified result"}}})
        self.manager.on_event({"method": "turn/completed", "params": {"threadId": worker["worker"]["id"], "turn": {"id": self.manager.store.task(task["task_id"])["turn"], "status": "completed"}}})
        with patch("time.time", return_value=1062):
            self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(task["task_id"])["result"], "late verified result")
        self.assertEqual(self.manager.store.task(later["task_id"])["state"], "RUNNING")

    def test_explicit_cancel_can_interrupt_a_timed_out_task(self):
        with patch("time.time", return_value=1000):
            worker = self.opened(kind="temp")
            task = self.send(worker, minutes=1)
            self.manager._schedule_once()
        with patch("time.time", return_value=1061):
            self.manager._schedule_once()
        self.manager.cancel(task["task_id"], "router-a")
        self.assertEqual(self.fake.threads[worker["worker"]["id"]]["status"]["type"], "idle")
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "CANCELLED")

    def test_running_task_cancel_keeps_the_normal_result_event(self):
        worker = self.opened()
        task = self.send(worker)
        self.manager._dispatch(self.manager.store.task(task["task_id"]))
        self.manager.cancel(task["task_id"], "router-a")
        events = self.manager.store.rows("SELECT payload FROM events WHERE kind='result' AND task=?", (task["task_id"],))
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(events[0]["payload"])["state"], "CANCELLED")

    def test_idle_restart_checks_queued_temps_of_other_routers(self):
        self.send(self.opened(kind="temp", router="router-b"))
        with self.assertRaisesRegex(ValueError, "QUEUED|temporary"):
            self.request("shutdown_when_idle", timeout=0)
        self.assertEqual(self.shutdown, [])
        self.assertFalse(self.manager.draining)

    def test_queued_temp_can_finish_while_idle_restart_waits(self):
        worker = self.opened(kind="temp", router="router-b")
        task = self.send(worker)
        checked = threading.Event()
        original = self.manager.idle_blockers
        outcome = []

        def check():
            blockers = original()
            checked.set()
            return blockers

        def stop():
            try:
                outcome.append(self.request("shutdown_when_idle", timeout=2))
            except Exception as error:
                outcome.append(error)

        with patch.object(self.manager, "idle_blockers", side_effect=check):
            waiter = threading.Thread(target=stop)
            waiter.start()
            try:
                self.assertTrue(checked.wait(1))
                self.manager._schedule_once()
                turn = self.manager.store.task(task["task_id"])["turn"]
                self.fake.complete(worker["worker"]["id"], "completed while draining")
                self.manager.on_event({"method": "turn/completed", "params": {"threadId": worker["worker"]["id"],
                                       "turn": {"id": turn, "status": "completed", "items": [{"type": "agentMessage", "text": "completed while draining"}]}}})
            finally:
                waiter.join(3)
        self.assertFalse(waiter.is_alive())
        self.assertEqual(outcome, [{"stopping": True, "native_codex_stopped": False}])
        self.assertEqual(self.manager.store.task(task["task_id"])["result"], "completed while draining")

    def test_idle_shutdown_atomically_closes_admission_and_scheduler(self):
        worker = self.opened()
        self.request("shutdown_when_idle", timeout=0)
        self.assertEqual(self.shutdown, [True])
        self.assertTrue(self.manager.draining)
        with self.assertRaisesRegex(ValueError, "restart|stopping|drain"):
            self.send(worker)
        self.manager._schedule_once()
        self.assertEqual(self.fake.started, [])

    def test_native_inspection_exceeding_timeout_never_stops_the_daemon(self):
        with patch.object(self.manager, "idle_blockers", return_value=[]), \
                patch("claude_codex_workflow.service.time.monotonic", side_effect=[0, 2]):
            with self.assertRaisesRegex(ValueError, "timeout|Timeout"):
                self.request("shutdown_when_idle", timeout=1)
        self.assertFalse(self.manager.draining)
        self.assertEqual(self.shutdown, [])

    def test_sender_racing_the_final_idle_check_cannot_enqueue_a_temp(self):
        worker = self.opened(kind="temp")
        checked, proceed, attempted, sent = (threading.Event() for _ in range(4))
        errors = []

        def check():
            checked.set()
            if not proceed.wait(3):
                raise RuntimeError("Idle-check test timed out")
            return []

        def sender():
            attempted.set()
            try:
                self.send(worker)
            except ValueError as error:
                errors.append(str(error))
            finally:
                sent.set()

        with patch.object(self.manager, "idle_blockers", side_effect=check):
            stop = threading.Thread(target=lambda: self.request("shutdown_when_idle", timeout=0))
            send = threading.Thread(target=sender)
            stop.start()
            try:
                self.assertTrue(checked.wait(2))
                send.start()
                self.assertTrue(attempted.wait(2))
                self.assertFalse(sent.wait(.05))
            finally:
                proceed.set()
                stop.join(3)
                if send.ident is not None:
                    send.join(3)
        self.assertEqual(len(errors), 1)
        self.assertIn("restart", errors[0])
        self.assertEqual(self.manager.store.rows("SELECT * FROM tasks"), [])

    def test_expired_formal_native_turn_also_blocks_idle_shutdown(self):
        with patch("time.time", return_value=1000):
            task = self.send(self.opened(), minutes=1)
            self.manager._schedule_once()
        with patch("time.time", return_value=1061):
            self.manager._schedule_once()
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "BLOCKED")
        with self.assertRaisesRegex(ValueError, "native"):
            self.request("shutdown_when_idle", timeout=0)

    def test_missing_temp_active_identity_is_never_guessed_from_old_tasks(self):
        with patch("time.time", return_value=1000):
            worker = self.opened(kind="temp")
            task = self.send(worker, minutes=1)
            self.manager._schedule_once()
        with patch("time.time", return_value=1061):
            self.manager._schedule_once()
        thread = worker["worker"]["id"]
        self.manager.store.execute("UPDATE workers SET active_turn=NULL WHERE id=?", (thread,))
        self.manager.reconcile(self.manager.store.worker(thread))
        self.assertEqual(self.manager.store.worker(thread)["active_turn"], "unknown")
        self.manager.cancel(task["task_id"], "router-a")
        self.assertEqual(self.fake.threads[thread]["status"]["type"], "active")

    def test_legacy_shutdown_also_rejects_queued_temps(self):
        self.send(self.opened(kind="temp"))
        with self.assertRaisesRegex(ValueError, "temporary|QUEUED"):
            self.request("shutdown")
        self.assertEqual(self.shutdown, [])

    def test_recovered_temp_is_not_replayed_but_native_writer_is_retained(self):
        worker = self.opened(kind="temp")
        task = self.send(worker)
        self.manager._dispatch(self.manager.store.task(task["task_id"]))
        self.manager.recover()
        self.assertEqual(self.manager.store.task(task["task_id"])["state"], "INCONCLUSIVE")
        self.assertIsNotNone(self.manager.store.worker(worker["worker"]["id"])["active_turn"])
        with self.assertRaisesRegex(ValueError, "native|temporary|idle"):
            self.request("shutdown_when_idle", timeout=0)
        self.assertEqual(len(self.fake.started), 1)

    def test_doctor_reports_running_release_and_current_mismatch(self):
        with patch("claude_codex_workflow.service.current_release", return_value="/synthetic/releases/new"), \
                patch("shutil.which", return_value=None):
            doctor = self.request("doctor")
        self.assertEqual(doctor["daemon_release"], self.manager.release)
        self.assertEqual(doctor["current_release"], "/synthetic/releases/new")
        self.assertFalse(doctor["daemon_current_matches"])


class DeploymentCommandTests(unittest.TestCase):
    def test_custom_install_release_checks_its_own_current_link(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            old = base / "releases/old"
            new = base / "releases/new"
            old.mkdir(parents=True)
            new.mkdir()
            (base / "current").symlink_to(new, target_is_directory=True)
            with patch("claude_codex_workflow.service.RUNTIME_RELEASE", str(old)):
                self.assertEqual(service.current_release(), str(new))

    def test_restart_cli_uses_the_atomic_helper(self):
        with patch("claude_codex_workflow.cli.restart_daemon", return_value={"restarted": True}) as restart, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["daemon", "--restart", "--when-idle", "--timeout", "12"]), 0)
        restart.assert_called_once_with(timeout=12)
        self.assertTrue(json.loads(output.getvalue())["result"]["restarted"])

    def test_installer_reports_old_daemon_even_when_application_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch("claude_codex_workflow.install.peek_runtime", return_value={"daemon_release": "/synthetic/releases/old", "version": "0.2.1"}):
            for _ in range(2):
                result = install(Path(temp), "router", True)
                self.assertTrue(result["daemon_restart_needed"])
                self.assertIn("daemon --restart --when-idle", result["recommended_daemon_command"])

    def test_atomic_restart_waits_for_old_process_exit_before_starting_new(self):
        with tempfile.TemporaryDirectory() as temp:
            order = []
            def rpc(operation, *args, **kwargs):
                order.append(operation)
                return {"stopping": True} if operation == "shutdown_when_idle" else {"daemon_release": "new"}
            with patch("claude_codex_workflow.service.call", side_effect=rpc), \
                    patch("claude_codex_workflow.service.wait_for_stop", side_effect=lambda *args, **kwargs: order.append("exited")):
                result = service.restart_daemon(root=Path(temp), timeout=12)
            self.assertEqual(order, ["shutdown_when_idle", "exited", "runtime_info"])
            self.assertTrue(result["restarted"])

    def test_unsupported_legacy_daemon_is_never_stopped_through_unsafe_fallback(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch("claude_codex_workflow.service.call", side_effect=ValueError("Unknown coordinator operation")) as rpc:
            with self.assertRaisesRegex(RuntimeError, "atomic|upgrade"):
                service.restart_daemon(root=Path(temp), timeout=0)
            self.assertEqual([c.args[0] for c in rpc.call_args_list], ["shutdown_when_idle"])

    def test_restart_timeout_does_not_start_a_replacement(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch("claude_codex_workflow.service.call", side_effect=ValueError("Coordinator not idle: QUEUED")) as rpc:
            with self.assertRaisesRegex(ValueError, "not idle"):
                service.restart_daemon(root=Path(temp), timeout=0)
            self.assertEqual([c.args[0] for c in rpc.call_args_list], ["shutdown_when_idle"])

    def test_replacement_release_mismatch_is_reported_without_another_stop(self):
        replies = [{"stopping": True}, {"current_release": "new", "daemon_current_matches": False}]
        with tempfile.TemporaryDirectory() as temp, \
                patch("claude_codex_workflow.service.call", side_effect=replies) as rpc, \
                patch("claude_codex_workflow.service.wait_for_stop"):
            with self.assertRaisesRegex(RuntimeError, "release|current"):
                service.restart_daemon(root=Path(temp), timeout=1)
            self.assertEqual([c.args[0] for c in rpc.call_args_list], ["shutdown_when_idle", "runtime_info"])

    def test_restart_over_real_control_socket_with_fake_native_daemons(self):
        # Both processes and their state belong to this test, never the installed daemon.
        source = str(Path(__file__).resolve().parents[1] / "src")
        test_source = str(Path(__file__).resolve().parent)
        script = """
import os
from claude_codex_workflow import service
from claude_codex_workflow.manager import Manager
from test_workflow import FakeNative
service.Manager = lambda root, native_socket=None: Manager(root, client=FakeNative())
service.current_release = lambda: service.RUNTIME_RELEASE
service.serve(root=os.environ['CCW_HOME'])
"""
        processes = []
        popen = subprocess.Popen
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            env = {**os.environ, "CCW_HOME": temp, "PYTHONPATH": source + os.pathsep + test_source}
            first = popen([sys.executable, "-c", script], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(first)
            try:
                deadline = time.monotonic() + 5
                while not (root / "control.sock").exists():
                    if time.monotonic() >= deadline or first.poll() is not None:
                        self.fail("Fake daemon did not start")
                    time.sleep(.02)
                old_pid = (root / "service.pid").read_text()

                def spawn(*args, **kwargs):
                    kwargs["env"] = env
                    process = popen([sys.executable, "-c", script], **kwargs)
                    processes.append(process)
                    return process

                with patch("claude_codex_workflow.service.subprocess.Popen", side_effect=spawn):
                    result = service.restart_daemon(root=root, timeout=1)
                self.assertTrue(result["restarted"])
                self.assertNotEqual((root / "service.pid").read_text(), old_pid)
                first.wait(timeout=5)
                service.call("shutdown_when_idle", {"timeout": 0}, root=root, autostart=False)
                processes[-1].wait(timeout=5)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)


class CompatibilityAndCacheTests(unittest.TestCase):
    def test_new_old_and_schema_two_databases_remain_readable_by_schema_one_check(self):
        for version in [None, "1", "2"]:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                if version is not None:
                    with sqlite3.connect(Path(temp) / "state.sqlite3") as old:
                        old.execute("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
                        old.execute("INSERT INTO meta VALUES('schema',?)", (version,))
                        old.execute("INSERT INTO meta VALUES('preserve','existing')")
                with Store(temp) as store:
                    self.assertEqual(store.one("SELECT value FROM meta WHERE key='schema'")["value"], "1")
                    store.start_takeover("router-a", [temp], "quota", 2)
                    if version:
                        self.assertEqual(store.one("SELECT value FROM meta WHERE key='preserve'")["value"], "existing")
                with sqlite3.connect(Path(temp) / "state.sqlite3") as legacy:
                    self.assertEqual(legacy.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0], "1")

    def test_worktree_queries_are_cached_and_eventually_refreshed(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = Path(temp) / "left", Path(temp) / "right"
            left.mkdir()
            right.mkdir()
            run = subprocess.run
            with patch("claude_codex_workflow.paths.time.monotonic", return_value=100), \
                    patch("claude_codex_workflow.paths.subprocess.run", wraps=run) as query:
                for _ in range(20):
                    self.assertFalse(paths.write_overlap(left, right))
                self.assertLessEqual(query.call_count, 2)
            subprocess.run(["git", "init", "-q", str(left)], check=True)
            with patch("claude_codex_workflow.paths.time.monotonic", return_value=1000):
                self.assertEqual(paths.worktree_root(left), left)

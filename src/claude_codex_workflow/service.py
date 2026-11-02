"""Local-only control socket for the coordinator; no remote TCP listener."""
from __future__ import annotations

import fcntl
import json
import os
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import __version__
from .manager import Manager, RUNTIME_RELEASE


def public(value):
    if isinstance(value, dict):
        return {key: public(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [public(item) for item in value]
    return value


def state_root():
    return Path(os.environ.get("CCW_HOME", Path.home() / ".local/state/claude-codex-workflow")).expanduser()


def current_release():
    running = Path(RUNTIME_RELEASE)
    base = running.parent.parent if running.parent.name == "releases" else Path.home() / ".local/share/claude-codex-workflow"
    current = base / "current"
    return str(current.resolve()) if current.exists() else None


def runtime_info(manager):
    current = current_release()
    return {"version": __version__, "daemon_release": manager.release,
            "current_release": current, "daemon_current_matches": current == manager.release if current else None,
            "atomic_idle_restart": True, "ephemeral_reconnect": False}


def shutdown_when_idle(manager, timeout=0):
    if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 3600:
        raise ValueError("Idle timeout must be 0..3600 seconds")
    deadline = time.monotonic() + timeout
    while True:
        with manager.lock:
            if manager.draining:
                raise ValueError("Coordinator is already stopping for restart")
            blockers = manager.idle_blockers()
            if not blockers:
                if timeout > 0 and time.monotonic() > deadline:
                    raise ValueError("Idle timeout reached during native inspection; no stop was sent")
                # Admission, dispatch and this final check share the same lock.
                manager.draining = True
                manager.stopped.set()
                manager.shutdown()
                return {"stopping": True, "native_codex_stopped": False}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("Coordinator not idle: temporary tasks or native turns remain: " + json.dumps(blockers))
        if manager.stopped.wait(min(.2, remaining)):
            raise ValueError("Coordinator was stopped by another request")


def dispatch(manager, request):
    operation = request["operation"]
    p = request.get("params", {})
    store = manager.store
    methods = {"open": manager.open, "sync": manager.sync, "send": manager.send,
               "adopt": manager.adopt, "control": manager.control, "cancel": manager.cancel,
               "router": manager.register_router, "steer": manager.steer, "takeover": manager.takeover,
               "direct": manager.direct}
    if operation in methods:
        # Serialize control changes with dispatch, including the window before
        # the native turn ID has been returned. A cancel must not be overwritten
        # by a late RUNNING acknowledgment.
        with manager.lock:
            if manager.draining and operation not in {"sync", "cancel", "control"}:
                raise ValueError("Coordinator is stopping for restart; retry after it restarts")
            return methods[operation](**p)
    if operation in {"shutdown", "shutdown_when_idle"}:
        return shutdown_when_idle(manager, p.get("timeout", 0) if operation == "shutdown_when_idle" else 0)
    if operation == "runtime_info":
        return runtime_info(manager)
    if operation == "doctor":
        return {**runtime_info(manager), "native": manager.client.server_info,
                "native_socket": manager.native_socket, "registry": str(store.root),
                "tiers": {tier: manager.tier(tier) for tier in ["easy", "hard", "xhard"]}}
    if operation == "list":
        return store.roster(**p)
    if operation == "result":
        task = store.task(p["task_id"])
        if task["router"] != p["router"]:
            raise ValueError("Task belongs to a different Router")
        return task
    if operation == "inbox":
        return store.rows("SELECT id,worker,state,result,error,updated FROM tasks WHERE router=? AND state IN ('READY','BLOCKED','FAILED','INCONCLUSIVE') ORDER BY updated", (p["router"],))
    if operation == "review":
        return store.decide(**p)
    if operation == "events":
        rows = store.rows("SELECT e.* FROM events e LEFT JOIN workers w ON w.id=e.worker WHERE (w.router=? OR e.kind IN ('takeover_started','takeover_released','router_direct')) AND e.seq>? ORDER BY e.seq", (p["router"], p.get("after", 0)))
        return [row for row in rows if row["worker"] is not None or json.loads(row["payload"]).get("router") == p["router"]][:100]
    raise ValueError("Unknown coordinator operation")


def serve(root=None, native_socket=None):
    root = Path(root or state_root())
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lockfile = (root / "service.lock").open("a+")
    try:
        fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    os.chmod(root / "service.lock", 0o600)
    manager = Manager(root, native_socket=native_socket)
    path = root / "control.sock"
    if path.exists():
        path.unlink()  # Only after acquiring the instance's exclusive lock.

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(60)
            try:
                line = self.rfile.readline(1024 * 1024 + 1)
                if not line:
                    return
                if len(line) > 1024 * 1024:
                    raise ValueError("Coordinator request too large")
                response = {"ok": True, "result": public(dispatch(manager, json.loads(line)))}
            except Exception as error:
                response = {"ok": False, "error": str(error)}
            self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode())

    class Server(socketserver.ThreadingUnixStreamServer):
        daemon_threads = True

    server = Server(str(path), Handler)
    os.chmod(path, 0o600)
    (root / "service.pid").write_text(str(os.getpid()))
    os.chmod(root / "service.pid", 0o600)
    manager.start()

    def stop(*_):
        manager.stopped.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    manager.shutdown = stop
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        manager.close()
        server.server_close()
        path.unlink(missing_ok=True)
        lockfile.close()


def call(operation, params=None, root=None, autostart=True, timeout=60):
    root = Path(root or state_root())
    path = root / "control.sock"
    request = (json.dumps({"operation": operation, "params": params or {}}, ensure_ascii=False) + "\n").encode()
    for attempt in range(2):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(timeout)
        try:
            client.connect(str(path))
            client.sendall(request)
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = client.recv(65536)
                if not chunk:
                    raise RuntimeError("Coordinator disconnected; inspect its state before retrying a mutation")
                data.extend(chunk)
            response = json.loads(data)
            if not response["ok"]:
                raise ValueError(response["error"])
            return response["result"]
        except (FileNotFoundError, ConnectionRefusedError):
            if attempt or not autostart:
                raise RuntimeError("Coordinator unavailable; run ai-work daemon and inspect its private log")
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(root, 0o700)
            with (root / "service.log").open("ab") as log:
                os.chmod(root / "service.log", 0o600)
                source = Path(current_release() or RUNTIME_RELEASE) / "src"
                env = {**os.environ, "CCW_HOME": str(root), "PYTHONPATH": str(source) + os.pathsep + os.environ.get("PYTHONPATH", "")}
                subprocess.Popen([sys.executable, "-m", "claude_codex_workflow.cli", "daemon"], env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    probe.connect(str(path))
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    time.sleep(.1)
                finally:
                    probe.close()
        finally:
            client.close()


def wait_for_stop(root, timeout=15):
    deadline = time.monotonic() + timeout
    with (Path(root) / "service.lock").open("a+") as lock:
        os.chmod(lock.name, 0o600)
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Old coordinator has not exited; a second daemon was not started")
                time.sleep(.05)


def restart_daemon(timeout=300, root=None):
    if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 3600:
        raise ValueError("Idle timeout must be 0..3600 seconds")
    root = Path(root or state_root()).expanduser()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / "restart.lock").open("a+") as lock:
        os.chmod(lock.name, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another daemon restart is already in progress")
        try:
            call("shutdown_when_idle", {"timeout": timeout}, root=root, autostart=False, timeout=timeout + 30)
        except ValueError as error:
            if "Unknown coordinator operation" in str(error):
                raise RuntimeError("Running daemon lacks atomic idle-restart support; no stop was sent. Arrange a coordinated first upgrade") from error
            raise
        except RuntimeError as error:
            if "Coordinator unavailable" not in str(error):
                raise
        wait_for_stop(root)
        info = call("runtime_info", root=root)
        if info.get("daemon_current_matches") is False:
            raise RuntimeError("Replacement daemon release does not match current; inspect doctor before another restart")
        return {"restarted": True, "native_codex_stopped": False, "runtime": info}


def peek_runtime(home=Path.home()):
    # A fake install home must never reach the real user's daemon or autostart one.
    root = state_root() if Path(home).resolve() == Path.home().resolve() else Path(home) / ".local/state/claude-codex-workflow"
    if not (root / "control.sock").is_socket():
        return None
    try:
        return call("runtime_info", root=root, autostart=False, timeout=2)
    except ValueError as error:
        if "Unknown coordinator operation" not in str(error):
            return {"inspection_error": str(error), "daemon_release": None}
        try:
            old = call("doctor", root=root, autostart=False, timeout=2)
            return {"version": old.get("version"), "daemon_release": None, "atomic_idle_restart": False}
        except Exception as failure:
            return {"inspection_error": str(failure), "daemon_release": None, "atomic_idle_restart": False}
    except RuntimeError as error:
        return None if "Coordinator unavailable" in str(error) else {"inspection_error": str(error), "daemon_release": None}
    except OSError as error:
        return {"inspection_error": str(error), "daemon_release": None}

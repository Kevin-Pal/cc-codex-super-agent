"""One local coordinator, connected to the existing native Codex runtime."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .rpc import NativeClient, RpcError
from .paths import write_overlap
from .store import Store, TERMINAL
from . import workspaces

RUNTIME_RELEASE = str(Path(__file__).resolve().parents[2])


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def worker_name(router, direction):
    def clean(text, limit):
        text = re.sub(r"[\s_/\\\x00-\x1f]+", "-", text).strip("-.")
        if not text:
            raise ValueError("A readable Router and workstream name are required")
        return text[:limit]
    return "Worker_" + clean(router, 24) + "_" + clean(direction, 40)


def knowledge(cwd):
    root = Path(cwd)
    paths = ["AGENTS.md", "CLAUDE.md", "docs/project-state.md", "doc/TODO.md", "docs/TODO.md"]
    for entry in [root / "AGENTS.md", root / "CLAUDE.md"]:
        if entry.is_file():
            for target in re.findall(r"\]\(([^)]+\.md)(?:#[^)]*)?\)", entry.read_text()):
                if "://" in target:
                    continue
                candidate = (root / target.strip("<>")).resolve()
                if candidate.is_relative_to(root.resolve()) and len(paths) < 40:
                    paths.append(str(candidate.relative_to(root.resolve())))
    values = {}
    for rel in paths:
        p = root / rel
        if p.is_file():
            values[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, timeout=5)
    if r.returncode == 0:
        values["git_head"] = r.stdout.strip()
    return values


def messages(turn):
    result = []
    for item in turn.get("items", []):
        kind = item.get("type")
        if kind == "agentMessage":
            result.append({"role": "agent", "text": item.get("text", "")})
        elif kind == "userMessage":
            content = item.get("content", [])
            result.append({"role": "input", "text": "\n".join(x.get("text", "") for x in content if x.get("type") == "text")})
    return result


def native_policy(permission, kind):
    params = {"approvalPolicy": "never", "sandbox": "read-only" if permission == "independent-review" else "danger-full-access",
              "config": {}, "developerInstructions": "You are a Codex Worker coordinated by Claude Code. Follow the current delegated task and authentic direct human instructions. Keep shared project knowledge in project files. Do not spawn agents or publish/delete existing data/change production unless the task authorizes it. A broad sandbox is a capability, not authorization. Return observed evidence and unresolved issues; the Router owns acceptance."}
    if permission == "independent-review" or kind == "temp":
        params["config"].update({"memories.use_memories": False, "memories.generate_memories": False})
    return params


def missing_thread(error):
    try:
        if json.loads(str(error)).get("code") == -32601:
            return False
    except (ValueError, AttributeError):
        pass
    text = str(error).lower()
    return any(s in text for s in ("thread", "rollout")) and any(s in text for s in ("not loaded", "not found", "no rollout"))


class Manager:
    def __init__(self, root, native_socket=None, client=None):
        self.store = Store(root)
        self.lock = threading.RLock()
        self.dispatching = set()
        self.draining = False
        self.release = RUNTIME_RELEASE
        self.live_output = {}
        self.completed = {}
        self.stopped = threading.Event()
        self.native_socket = str(native_socket or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "app-server-control/app-server-control.sock")
        self.client = client or NativeClient(self.native_socket, self.on_event)
        self.model_cache = None
        self.last_scan = 0
        self.last_cleanup = 0
        self.scheduler = threading.Thread(target=self._schedule, daemon=True)
        self.recover()

    def start(self):
        self.scheduler.start()

    def close(self):
        self.stopped.set()
        self.client.close()
        if self.scheduler.is_alive():
            self.scheduler.join(timeout=3)
        if not self.scheduler.is_alive():
            self.store.close()

    def transient(self, error):
        return self.client.closed or isinstance(error, (TimeoutError, ConnectionError)) or any(
            s in str(error).lower() for s in ("connection lost", "connection closed", "connection is unavailable", "native connection unavailable"))

    def background_clear(self, worker_id, turn=None):
        jobs = self.client.request("thread/backgroundTerminals/list", {"threadId": worker_id, "limit": 1})
        if not isinstance(jobs, dict) or not isinstance(jobs.get("data"), list):
            raise ValueError("Native background response shape is unsupported; retain the workspace")
        clear = not jobs["data"] and not jobs.get("nextCursor")
        if clear and turn is not None:
            self.store.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               ("background-clear:" + worker_id, turn))
        return clear

    def restore_visibility(self, worker_id):
        try:
            self.client.request("thread/unarchive", {"threadId": worker_id})
        except RpcError as error:
            if "no archived rollout" not in str(error).lower():
                raise
            self.client.request("thread/read", {"threadId": worker_id})

    def owned(self, worker_id, router):
        worker = self.store.worker(worker_id)
        if worker["router"] != router:
            raise ValueError("Different Router owns this Worker; explicit control transfer is required")
        if worker["mode"] == "released":
            raise ValueError("Worker was released; explicitly adopt it again")
        return worker

    def models(self):
        if not self.model_cache or time.monotonic() - self.model_cache[0] > 300:
            response = self.client.request("model/list", {"limit": 100, "includeHidden": False})
            self.model_cache = (time.monotonic(), response.get("data", []))
        return self.model_cache[1]

    def tier(self, tier):
        family, effort = {"easy": ("luna", "max"), "hard": ("sol", "xhigh"), "xhard": ("astra", "xhigh")}[tier]
        helper = shutil.which("codex-tier")
        catalog = self.models()
        if helper:
            model = subprocess.check_output([helper, "model", tier], text=True, timeout=30).strip()
            effort = subprocess.check_output([helper, "effort", tier], text=True, timeout=30).strip()
        else:
            candidates = []
            for row in catalog:
                name = row.get("model", row["id"])
                match = re.fullmatch(r"gpt-(\d+)(?:\.(\d+))?-" + family, name)
                if match:
                    candidates.append(((int(match[1]), int(match[2] or 0)), name))
            if not candidates:
                raise ValueError("No supported model in requested tier family")
            model = max(candidates)[1]
        match = next((r for r in catalog if r.get("model", r["id"]) == model), None)
        allowed = {r["reasoningEffort"] for r in (match or {}).get("supportedReasoningEfforts", [])}
        if not match or effort not in allowed or not model.endswith("-" + family):
            raise ValueError("Tier mapping is unavailable or incompatible; no silent family fallback")
        return model, effort

    def register_router(self, router, name, cwd, rebind=False, reason=None):
        if not router or len(router) > 200:
            raise ValueError("Stable Router ID is required")
        cwd = str(Path(cwd).expanduser().resolve(strict=True))
        prior = self.store.one("SELECT value FROM meta WHERE key=?", ("project:" + router,))
        project = prior["value"] if prior else cwd
        if rebind:
            if not reason or not reason.strip():
                raise ValueError("An explicit project rebind needs a reason")
            if self.store.one("SELECT id FROM workspaces WHERE router=? AND state!='CLEANED'", (router,)):
                raise ValueError("Resolve managed workspaces before rebinding the project")
            for worker in self.store.rows("SELECT * FROM workers WHERE router=? AND mode!='released'", (router,)):
                if worker["active_turn"] or self.store.one("SELECT id FROM tasks WHERE worker=? AND state IN ('QUEUED','DISPATCHING','RUNNING')", (worker["id"],)):
                    raise ValueError("Finish pending work before rebinding the project")
                native = self.client.request("thread/read", {"threadId": worker["id"]})["thread"]
                if native.get("status", {}).get("type") == "active":
                    raise ValueError("A native turn is active; project rebind refused")
            project = cwd
        self.store.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           ("project:" + router, project))
        self.store.execute("INSERT INTO routers VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,cwd=excluded.cwd,updated=excluded.updated",
                           (router, name, project, time.time()))
        for worker in self.store.rows("SELECT * FROM workers WHERE router=? AND origin IN ('worker','temp')", (router,)):
            self.store.execute("INSERT INTO worker_projects VALUES(?,?,NULL) ON CONFLICT(worker) DO UPDATE SET project_root=excluded.project_root",
                               (worker["id"], project))
        if rebind:
            self.store.event("project_rebound", payload={"router": router, "project_root": project, "reason": reason})
        return {"router": router, "name": name, "cwd": project, "project_root": project,
                "observed_cwd": cwd, "cwd_drift": project != cwd}

    def project(self, worker):
        row = self.store.one("SELECT * FROM worker_projects WHERE worker=?", (worker["id"],))
        return row or {"project_root": worker["cwd"], "workspace": None}

    def check_path(self, worker, native=None):
        if not Path(worker["cwd"]).is_dir():
            raise ValueError("Worker execution directory is missing; inspect its registered environment")
        native = native or self.client.request("thread/read", {"threadId": worker["id"]})["thread"]
        if str(Path(native["cwd"]).resolve()) != str(Path(worker["cwd"]).resolve()):
            raise ValueError("Native cwd changed; inspect and explicitly repair the original thread before dispatch")
        if worker["kind"] == "worker" and worker["origin"] == "worker" and self.project(worker)["project_root"] != worker["cwd"]:
            raise ValueError("Formal Worker is outside its Router project; use repair, never open a replacement")

    def inspect(self, thread_id, router):
        # Read-only collaboration discovery. No ownership, cwd, permissions or turns change.
        native = self.client.request("thread/read", {"threadId": thread_id})["thread"]
        prior = self.store.one("SELECT router,kind,mode FROM workers WHERE id=?", (thread_id,))
        return {"thread_id": thread_id, "name": native.get("name"), "cwd": native["cwd"],
                "status": native.get("status"), "registration": prior,
                "control_changed": False, "requesting_router": router}

    def repair(self, worker_id, router, reason, reload=False):
        worker = self.owned(worker_id, router)
        if worker["kind"] != "worker" or worker["origin"] != "worker":
            raise ValueError("Only a Router-created formal Worker can be reanchored")
        if worker["mode"] in {"manual", "paused"}:
            raise ValueError("Return human control before path repair")
        if not reason or not reason.strip():
            raise ValueError("Path repair needs an explicit reason")
        if worker["active_turn"] or self.store.one("SELECT id FROM tasks WHERE worker=? AND state IN ('QUEUED','DISPATCHING','RUNNING')", (worker_id,)):
            raise ValueError("Finish pending work before path repair")
        native = self.client.request("thread/read", {"threadId": worker_id})["thread"]
        if native.get("status", {}).get("type") == "active":
            raise ValueError("Native turn is active; path repair refused")
        project = self.project(worker)["project_root"]
        if worker["stream"] and self.store.one("SELECT id FROM workers WHERE router=? AND stream=? AND kind='worker' AND mode!='released' AND id!=?", (router, worker["stream"], worker_id)):
            raise ValueError("Another live Worker has the same stream; resolve ownership before repair")
        params = {"threadId": worker_id, "cwd": project, "excludeTurns": True, **native_policy(worker["permission"], worker["kind"])}
        response = self.client.request("thread/resume", params)
        if str(Path(response["thread"]["cwd"]).resolve()) != project and reload:
            if self.client.request("thread/read", {"threadId": worker_id})["thread"].get("status", {}).get("type") == "active":
                raise ValueError("A native turn started; reload refused")
            children = self.client.request("thread/list", {"ancestorThreadId": worker_id, "limit": 1,
                "sourceKinds": ["cli", "vscode", "exec", "appServer", "subAgent", "subAgentReview",
                                "subAgentCompact", "subAgentThreadSpawn", "subAgentOther", "unknown"]})
            if not isinstance(children.get("data"), list):
                raise ValueError("Cannot verify descendant sessions before reload")
            if children["data"] or children.get("nextCursor"):
                raise ValueError("Reload could archive descendant sessions; coordinate them explicitly first")
            self.store.event("path_reload_started", worker=worker_id, payload={"old_cwd": worker["cwd"], "project_root": project, "reason": reason})
            self.store.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               ("path-reload:" + worker_id, json.dumps({"project_root": project, "old_cwd": worker["cwd"], "reason": reason})))
            try:
                self.client.request("thread/archive", {"threadId": worker_id})
                self.client.request("thread/unarchive", {"threadId": worker_id})
                response = self.client.request("thread/resume", params)
            except Exception as error:
                # Restore visibility if a later step failed; never create/fork another ID.
                try:
                    self.restore_visibility(worker_id)
                    self.store.execute("DELETE FROM meta WHERE key=?", ("path-reload:" + worker_id,))
                except Exception:
                    pass
                self.store.event("path_reload_failed", worker=worker_id, payload={"error": str(error)[:500]})
                raise
        if response["thread"]["id"] != worker_id or str(Path(response["thread"]["cwd"]).resolve()) != project:
            raise ValueError("Native backend did not confirm the same thread at the intended project; inspect and use repair --reload only in an idle window")
        if response.get("approvalPolicy", "never") != "never":
            raise ValueError("Native approval policy differs after reload; inspect before dispatch")
        sandbox = response.get("sandbox", {})
        if sandbox and sandbox.get("type") != ("readOnly" if worker["permission"] == "independent-review" else "dangerFullAccess"):
            raise ValueError("Native sandbox differs after reload; inspect before dispatch")
        self.store.execute("UPDATE workers SET cwd=?,updated=? WHERE id=?", (project, time.time(), worker_id))
        self.store.event("path_repaired", worker=worker_id, payload={"old_cwd": worker["cwd"], "project_root": project, "reason": reason})
        self.store.execute("DELETE FROM meta WHERE key=?", ("path-reload:" + worker_id,))
        return {"worker": self.store.worker(worker_id), "instruction_sources": response.get("instructionSources", []), "sync": self.sync(worker_id, router)}

    def workspace(self, router, workspace_id=None, cleanup=False, discard=False, forget=False, reason=None):
        if sum(bool(x) for x in (cleanup, discard, forget)) > 1:
            raise ValueError("Choose cleanup, discard or forget separately")
        if workspace_id is None:
            if cleanup or discard or forget:
                raise ValueError("A workspace ID is required")
            return self.store.rows("SELECT * FROM workspaces WHERE router=? ORDER BY created", (router,))
        row = self.store.one("SELECT * FROM workspaces WHERE id=? AND router=?", (workspace_id, router))
        if not row:
            raise ValueError("Unknown owned workspace")
        if (discard or forget) and (not reason or not reason.strip()):
            raise ValueError("Discard/forget requires an explicit inspection reason")
        if row["state"] == "CLEANED":
            return row
        if forget:
            if row["worker"]:
                worker = self.store.worker(row["worker"])
                if worker["active_turn"] or worker["mode"] in {"manual", "paused"} or self.store.one("SELECT id FROM tasks WHERE worker=? AND state IN ('QUEUED','RUNNING','DISPATCHING')", (worker["id"],)):
                    raise ValueError("Finish pending work and return human control before forgetting a workspace")
            registered = Path(row["repo"]).exists() and row["path"] in workspaces.git(row["repo"], "worktree", "list", "--porcelain")
            if Path(row["path"]).exists() or registered:
                raise ValueError("Forget requires both the path and Git worktree registration to be absent")
            self.store.execute("UPDATE workspaces SET state='CLEANED' WHERE id=?", (workspace_id,))
            if row["worker"]:
                self.store.execute("UPDATE workers SET mode='released' WHERE id=?", (row["worker"],))
            self.store.event("workspace_forgotten", worker=row["worker"], payload={"resource": row, "reason": reason, "physical_changes": False})
            return self.workspace(router, workspace_id)
        if not cleanup and not discard:
            return row
        if row["state"] in {"STARTING", "UNCERTAIN", "NATIVE_CREATED"}:
            raise ValueError("Native creation outcome is unresolved; locate/stop the exact thread before manual recovery, never delete this environment blindly")
        if row["worker"]:
            worker = self.store.worker(row["worker"])
            if worker["active_turn"] or worker["mode"] in {"manual", "paused"}:
                raise ValueError("Workspace is active or under human control")
            tasks = self.store.rows("SELECT * FROM tasks WHERE worker=? ORDER BY created,id", (worker["id"],))
            if discard and any(t["state"] not in TERMINAL for t in tasks):
                raise ValueError("Finish/cancel pending tasks before discarding a workspace")
            if not discard and (not tasks or any(t["state"] != "ACCEPTED" for t in tasks)):
                raise ValueError("Accept all task results before workspace cleanup")
            try:
                native = self.client.request("thread/read", {"threadId": worker["id"]})["thread"]
                if native.get("status", {}).get("type") == "active":
                    raise ValueError("Native task still active")
                if not self.background_clear(worker["id"]):
                    raise ValueError("Native background terminals still exist; stop/verify them before cleanup")
            except RpcError as error:
                if not missing_thread(error):
                    raise
                snapshot = self.store.one("SELECT value FROM meta WHERE key=?", ("background-clear:" + worker["id"],))
                last_turn = next((t["turn"] for t in reversed(tasks) if t["turn"]), "unused")
                if not tasks or not snapshot or snapshot["value"] != last_turn:
                    raise ValueError("Native background state is unknown; workspace retained")
            # Process/open-file checks happen in workspaces.remove.
        result = workspaces.remove(self.store, row)
        if row["worker"]:
            self.store.execute("UPDATE workers SET mode='released' WHERE id=?", (row["worker"],))
            try:
                self.client.request("thread/unsubscribe", {"threadId": row["worker"]})
            except RpcError:
                pass  # No active turn/jobs remain; a temp may already be unloaded.
        self.store.event("workspace_cleaned", worker=row["worker"], payload=result)
        return result

    def review(self, task_id, router, accepted, note):
        task = self.store.decide(task_id, router, accepted, note)
        resource = self.project(self.store.worker(task["worker"]))["workspace"]
        if accepted and resource:
            try:
                task["workspace_cleanup"] = self.workspace(router, resource, cleanup=True)
            except (ValueError, subprocess.SubprocessError, OSError, RpcError) as error:
                task["workspace_retained"] = str(error)[:1000]
        return task

    def worker_overlap(self, left, right):
        if not write_overlap(left["cwd"], right["cwd"]):
            return False
        for isolated, other in [(left, right), (right, left)]:
            resource = self.project(isolated)["workspace"]
            if resource:
                row = self.store.one("SELECT * FROM workspaces WHERE id=? AND state!='CLEANED'", (resource,))
                if row:
                    try:
                        path = workspaces.verified(row)
                    except (ValueError, subprocess.SubprocessError, OSError):
                        return True
                    if not Path(other["cwd"]).resolve().is_relative_to(path):
                        # Only the registered main-project writer excludes this managed namespace.
                        if other["cwd"] == row["project_root"] and other["kind"] == "worker":
                            return False
        return True

    def takeover(self, router, scope=None, reason=None, hours=2, release=False, status=False, note=None):
        with self.lock:
            if not isinstance(router, str) or not router or len(router) > 200:
                raise ValueError("Stable Router ID is required")
            if release and status or (release or status) and (scope is not None or reason is not None):
                raise ValueError("Choose scope/reason, release or status as separate takeover modes")
            if note is not None and not release:
                raise ValueError("A takeover note is only valid with release")
            if status:
                return {"router": router, "takeovers": self.store.active_takeovers(router)}
            if release:
                return {"router": router, "released": self.store.release_takeovers(router, note)}
            if not isinstance(scope, list) or not scope or any(not isinstance(p, str) or not p.strip() for p in scope):
                raise ValueError("At least one concrete takeover scope is required")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("A takeover reason is required")
            if not isinstance(hours, (int, float)) or not 0 < hours <= 8:
                raise ValueError("Takeover hours must be greater than 0 and at most 8")
            scopes = list(dict.fromkeys(str(Path(p).expanduser().resolve()) for p in scope))
            self.admit_router_write(router, scopes, "takeover")
            return self.store.start_takeover(router, scopes, reason.strip(), hours)

    def admit_router_write(self, router, paths, action):
        """One admission rule for every Claude-side write window (takeover and direct).

        Callers hold self.lock, so the decision is serialized with dispatch.
        """
        for worker in self.writers():
            if any(write_overlap(worker["cwd"], path) for path in paths):
                raise ValueError(f"A writer is RUNNING/DISPATCHING in this worktree; cancel and sync it before {action}")
        for worker in self.store.rows("SELECT * FROM workers WHERE mode='manual'"):
            if any(write_overlap(worker["cwd"], path) for path in paths):
                raise ValueError("An overlapping Worker is under manual control; sync and obtain human confirmation before changing control")
        for takeover in self.store.active_takeovers():
            if takeover["router"] != router and any(write_overlap(a, b) for a in paths for b in takeover["scope"]):
                raise ValueError(f"Another Router already has an overlapping takeover; release and sync before {action}")
        for lease in self.live_leases():
            if lease["router"] != router and any(write_overlap(path, lease["path"]) for path in paths):
                raise ValueError(f"Another Router holds an overlapping microtask lease; wait for it to expire before {action}")

    def live_leases(self):
        return self.store.rows("SELECT * FROM leases WHERE expires>?", (time.time(),))

    def direct(self, router, paths, reason, seconds=300):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A concrete short-path reason is required")
        if not isinstance(seconds, (int, float)) or not 1 <= seconds <= 600:
            raise ValueError("Microtask lease must be 1..600 seconds")
        resolved = []
        for raw in paths:
            path = str(Path(raw).expanduser().resolve())
            if Path(path).is_dir():
                raise ValueError("A microtask lease names exact files, not whole directories")
            resolved.append(path)
        self.admit_router_write(router, resolved, "a microtask")
        for path in resolved:
            self.store.execute("INSERT INTO leases VALUES(?,?,?,?) ON CONFLICT(router,path) DO UPDATE SET expires=excluded.expires,reason=excluded.reason",
                               (router, path, time.time() + seconds, reason))
        # The event enters overlapping Workers' sync tokens, like takeover events.
        self.store.event("router_direct", payload={"router": router, "paths": resolved, "reason": reason, "label": "Router direct work"})
        return {"paths": resolved, "expires_in": seconds, "verification_required": True}

    def write_blockers(self, cwd):
        """Claude-side windows (takeovers and live microtask leases) overlapping a Worker cwd."""
        return self.takeover_conflicts(cwd) + [lease for lease in self.live_leases() if write_overlap(cwd, lease["path"])]

    def takeover_conflicts(self, cwd):
        return [takeover for takeover in self.store.active_takeovers()
                if any(write_overlap(cwd, path) for path in takeover["scope"])]

    def takeover_events(self, cwd):
        self.store.active_takeovers()  # Materialize automatic expiry before calculating sync tokens.
        events = []
        for row in self.store.rows("SELECT seq,kind,payload,created FROM events WHERE kind IN ('takeover_started','takeover_released','router_direct') ORDER BY seq"):
            payload = json.loads(row["payload"])
            if any(write_overlap(cwd, path) for path in payload.get("scope") or payload.get("paths") or []):
                events.append({**payload, "seq": row["seq"], "kind": row["kind"], "event_time": row["created"]})
        return events

    def open(self, router, router_name, cwd, direction, stream=None, kind="worker", tier="hard", permission="trusted-worker", isolation="none", repo=None, base=None):
        with self.lock:
            if self.draining:
                raise ValueError("Coordinator is stopping for restart; retry after it restarts")
            binding = self.store.one("SELECT value FROM meta WHERE key=?", ("project:" + router,))
            if not binding:
                raise ValueError("Register the Router launch project first (hook or ai-work router --cwd PROJECT); open never guesses a project")
            cwd = cwd or binding["value"]
            registration = self.register_router(router, router_name, cwd)
            if str(Path(cwd).expanduser().resolve()) != registration["project_root"]:
                raise ValueError("Worker creation must use the Router project path; task directories do not create a new team")
            cwd = project = registration["project_root"]
            if kind not in {"worker", "temp"}:
                raise ValueError("Existing personal sessions use adopt, not open")
            if permission not in {"trusted-worker", "independent-review"}:
                raise ValueError("Unknown permission template")
            if isolation not in {"none", "worktree"} or isolation != "none" and kind != "temp":
                raise ValueError("Only temporary Workers may request worktree isolation")
            if isolation == "none" and (repo is not None or base is not None):
                raise ValueError("Repository/base options require temp worktree isolation")
            if kind == "worker":
                if not stream:
                    raise ValueError("A stable workstream key is required for a persistent Worker")
                candidates = self.store.rows("SELECT * FROM workers WHERE router=? AND stream=? AND kind='worker' AND mode!='released'", (router, stream))
                if len(candidates) > 1:
                    raise ValueError("Multiple legacy Workers have this stream; inspect exact IDs and release the unwanted registration before repair/reuse")
                prior = candidates[0] if candidates else None
                if prior:
                    self.check_path(prior)
                    return {"worker": prior, "sync": self.sync(prior["id"], router)}
            model, effort = self.tier(tier)
            resource = None
            if isolation == "worktree":
                pending = self.store.one("SELECT id FROM workspaces WHERE router=? AND worker IS NULL AND state!='CLEANED'", (router,))
                if pending:
                    raise ValueError("Resolve prepared/uncertain workspace before another open: " + pending["id"])
                resource, cwd = workspaces.prepare(self.store, router, project, repo, base)
            params = {"cwd": cwd, "model": model, **native_policy(permission, kind),
                      "ephemeral": kind == "temp", "serviceName": "claude-codex-workflow",
                      }
            params["config"]["model_reasoning_effort"] = effort
            if resource:
                self.store.execute("UPDATE workspaces SET state='STARTING' WHERE id=?", (resource,))
            try:
                response = self.client.request("thread/start", params)
            except Exception as error:
                if resource:
                    self.store.execute("UPDATE workspaces SET state='UNCERTAIN' WHERE id=?", (resource,))
                    raise ValueError("Native start failed/uncertain; workspace retained: " + resource + ". Inspect native work before retry/cleanup. " + str(error)) from error
                raise
            native = response["thread"]
            if resource:
                self.store.execute("UPDATE workspaces SET state='NATIVE_CREATED' WHERE id=?", (resource,))
            name = "" if kind == "temp" else worker_name(router_name, direction)
            if name and self.store.one("SELECT id FROM workers WHERE name=?", (name,)):
                name += "_" + native["id"][-6:]
            if name:
                self.client.request("thread/name/set", {"threadId": native["id"], "name": name})
            try:
                worker = self.store.register(native["id"], kind, router, name, cwd, tier, permission, stream,
                                             project_root=project, workspace=resource)
            except Exception as error:
                if resource:
                    raise ValueError("Registration failed; retain workspace " + resource + " and native thread " + native["id"] + " for inspection") from error
                raise
            return {"worker": worker, "sync": self.sync(worker["id"], router),
                    "instruction_sources": response.get("instructionSources", []), "model": model, "effort": effort}

    def adopt(self, thread_id, router, router_name, from_router=None):
        with self.lock:
            if not self.store.one("SELECT value FROM meta WHERE key=?", ("project:" + router,)):
                raise ValueError("Register the requesting Router project before external adoption")
            prior = self.store.one("SELECT * FROM workers WHERE id=?", (thread_id,))
            if prior and prior["router"] == router and prior["origin"] == "worker" and prior["mode"] != "released":
                return {"worker": prior, "sync": self.sync(thread_id, router)}
            if prior and prior["router"] != router:
                if from_router != prior["router"]:
                    raise ValueError("Name the previous Router explicitly for takeover")
                if self.store.one("SELECT id FROM tasks WHERE worker=? AND state IN ('QUEUED','DISPATCHING','RUNNING')", (thread_id,)):
                    raise ValueError("Previous Router has pending work; pause/cancel it before transfer")
            native = self.client.request("thread/read", {"threadId": thread_id})["thread"]
            if native.get("ephemeral"):
                raise ValueError("A temporary native thread cannot be silently adopted as persistent")
            if native.get("status", {}).get("type") == "active":
                raise ValueError("Thread is active; wait or explicitly coordinate its active turn first")
            self.register_router(router, router_name, native["cwd"])
            cwd = str(Path(native["cwd"]).expanduser().resolve(strict=True))
            if prior:
                origin = prior["origin"] if prior["router"] == router else "user-selected"
                mode = prior["mode"] if prior["router"] == router and prior["mode"] != "released" else "automatic"
                self.store.execute("UPDATE workers SET router=?,cwd=?,origin=?,mode=?,updated=? WHERE id=?", (router, cwd, origin, mode, time.time(), thread_id))
            else:
                self.store.register(thread_id, "personal", router, native.get("name") or "", cwd, origin="user-selected")
            project = self.store.one("SELECT value FROM meta WHERE key=?", ("project:" + router,))["value"] if prior and prior["router"] == router and prior["origin"] == "worker" else cwd
            self.store.execute("INSERT INTO worker_projects VALUES(?,?,NULL) ON CONFLICT(worker) DO UPDATE SET project_root=excluded.project_root,workspace=NULL", (thread_id, project))
            self.client.request("thread/resume", {"threadId": thread_id, "excludeTurns": True})
            self.store.event("adopted", worker=thread_id, payload={"router": router, "previous_router": from_router})
            return {"worker": self.store.worker(thread_id), "sync": self.sync(thread_id, router)}

    def turns(self, worker):
        try:
            return self.client.request("thread/turns/list", {"threadId": worker["id"], "limit": 20, "sortDirection": "desc", "itemsView": "full"}).get("data", [])
        except RpcError as error:
            if worker["kind"] == "temp" or "not found" in str(error).lower():
                return []
            raise

    def sync(self, worker_id, router, history=False):
        worker = self.owned(worker_id, router)
        native = self.client.request("thread/read", {"threadId": worker_id})["thread"]
        turns = self.turns(worker)
        own = {r["turn"] for r in self.store.rows("SELECT turn FROM tasks WHERE worker=? AND turn IS NOT NULL", (worker_id,))}
        external = [{"id": t["id"], "status": t.get("status"), "messages": messages(t)} for t in turns if t["id"] not in own]
        project = self.project(worker)
        files = knowledge(project["project_root"])
        if project["workspace"]:
            files["execution_head"] = workspaces.git(worker["cwd"], "rev-parse", "HEAD")
            files["execution_status"] = digest(workspaces.git(worker["cwd"], "status", "--porcelain", "--untracked-files=normal"))
        direct_work = self.takeover_events(worker["cwd"])
        # A baseline captured during a microtask is provisional: the file may
        # change after sync without a Git commit or shared-memory edit. Expiry
        # must invalidate it too, rather than only recording the initial grant.
        microtasks = [lease for lease in self.live_leases() if write_overlap(worker["cwd"], lease["path"])]
        baseline = {"external": external, "knowledge": files, "router_direct_work": [e["seq"] for e in direct_work]}
        if microtasks:
            baseline["active_microtasks"] = sorted(microtasks, key=lambda lease: (lease["router"], lease["path"]))
        token = digest(baseline)
        fingerprints = {t["id"]: digest({"status": t.get("status"), "messages": messages(t)}) for t in turns}
        previous = self.store.one("SELECT value FROM meta WHERE key=?", ("view:" + worker_id,))
        acknowledged = json.loads(previous["value"]) if previous else {}
        fingerprints["_takeover_seq"] = max((e["seq"] for e in direct_work), default=0)
        selected = [t for t in turns if history or acknowledged.get(t["id"]) != fingerprints[t["id"]]]
        rendered = []
        budget = 64000 if history else 8000
        for turn in selected[:8]:
            output = []
            for message in messages(turn):
                length = min(budget, 6000 if history else 2500)
                if length <= 0:
                    break
                output.append({**message, "text": message["text"][-length:]})
                budget -= len(output[-1]["text"])
            if not output:
                break
            rendered.append({"id": turn["id"], "status": turn.get("status"), "external": turn["id"] not in own, "messages": output})
        if native.get("name") and native["name"] != worker["name"]:
            self.store.execute("UPDATE workers SET name=? WHERE id=?", (native["name"], worker_id))
        return {"thread_id": worker_id, "sync_token": token, "status": native.get("status"),
                "external_turn_ids": [turn["id"] for turn in turns if turn["id"] not in own],
                "mode": worker["mode"], "project_knowledge": files,
                "project_root": project["project_root"], "execution_cwd": worker["cwd"], "workspace": project["workspace"],
                "active_microtasks": microtasks,
                "recent_turns": rendered, "history_truncated": len(rendered) < len(selected) or budget <= 0,
                "router_direct_work": [e for e in direct_work if history or e["seq"] > acknowledged.get("_takeover_seq", 0)],
                "_takeover_history": direct_work, "_fingerprints": fingerprints}

    def send(self, worker_id, router, prompt, authorization, sync_token=None, key=None, tier=None, minutes=45, queue_minutes=45):
        with self.lock:
            if self.draining:
                raise ValueError("Coordinator is stopping for restart; retry after it restarts")
            worker = self.owned(worker_id, router)
            self.check_path(worker)
            if worker["mode"] in {"paused", "manual"}:
                raise ValueError("Worker is paused or under human control; resume explicitly")
            if worker["permission"] != "independent-review" and self.takeover_conflicts(worker["cwd"]):
                raise ValueError("Active Router takeover in this worktree; release the takeover and sync before dispatch")
            view = self.sync(worker_id, router)
            if worker["kind"] != "temp" and sync_token != view["sync_token"]:
                raise ValueError("Project or external conversation changed; run sync and supply its exact sync_token")
            for turn_id in view["external_turn_ids"]:
                self.store.event("external_acknowledged", worker=worker_id, payload={"turn_id": turn_id}, key="external:" + turn_id)
            self.store.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               ("view:" + worker_id, json.dumps(view["_fingerprints"])))
            model, effort = self.tier(tier or worker["tier"])
            key = key or digest({"worker": worker_id, "prompt": prompt, "authorization": authorization})
            if worker["mode"] == "external" and view.get("status", {}).get("type") != "active":
                self.store.execute("UPDATE workers SET mode='automatic' WHERE id=?", (worker_id,))
            task = self.store.enqueue(worker_id, router, key, prompt, authorization, model, effort, minutes, view["sync_token"], queue_minutes)
            return {"task_id": task["id"], "thread_id": worker_id, "state": task["state"], "key": key}

    def on_event(self, message):
        method, p = message.get("method", ""), message.get("params", {})
        if "id" in message and method:
            self.client._send_frame(json.dumps({"id": message["id"], "error": {"code": -32601, "message": "Unsupported interactive server request; return a blocked result to the Router"}}).encode())
            self.store.event("unsupported_request", payload={"method": method})
            return
        if method == "ccw/disconnected":
            self.store.event("connection_lost", payload=p)
            return
        worker_id = p.get("threadId") or p.get("thread", {}).get("id")
        if not worker_id or not self.store.one("SELECT id FROM workers WHERE id=?", (worker_id,)):
            return
        if method in {"turn/started", "turn/completed"}:
            turn = p.get("turn", {})
            if method == "turn/started":
                self.store.execute("UPDATE workers SET active_turn=?,updated=? WHERE id=?", (turn.get("id"), time.time(), worker_id))
            else:
                self.store.execute("UPDATE workers SET active_turn=NULL,updated=? WHERE id=? AND active_turn=?", (time.time(), worker_id, turn.get("id")))
            self.store.event(method, worker=worker_id, payload={"turn_id": turn.get("id"), "status": turn.get("status")}, key=method + ":" + str(turn.get("id")))
            if method == "turn/completed":
                self.completed[turn["id"]] = {**turn, "items": self.live_output.get(turn["id"], turn.get("items", []))}
        elif method == "item/completed" and p.get("item", {}).get("type") == "agentMessage":
            self.live_output.setdefault(p.get("turnId"), []).append(p["item"])
        elif method == "thread/name/updated":
            self.store.execute("UPDATE workers SET name=? WHERE id=?", (p.get("threadName", ""), worker_id))

    def recover(self):
        for row in self.store.rows("SELECT * FROM meta WHERE key LIKE 'path-reload:%'"):
            worker_id = row["key"][len("path-reload:"):]
            try:
                self.restore_visibility(worker_id)
                self.store.event("path_reload_interrupted", worker=worker_id, payload={"visibility_restored": True, "next": "inspect and repair the same ID"})
                self.store.execute("DELETE FROM meta WHERE key=?", (row["key"],))
            except Exception as error:
                self.store.event("path_reload_failed", worker=worker_id, payload={"error": str(error)[:500]})
        # Never replay an uncertain dispatch. Reconnect to the same native thread.
        for worker in self.store.rows("SELECT * FROM workers WHERE mode!='released'"):
            try:
                if worker["kind"] == "temp":
                    for task in self.store.rows("SELECT id FROM tasks WHERE worker=? AND state IN ('DISPATCHING','RUNNING','QUEUED')", (worker["id"],)):
                        self.store.finish(task["id"], "INCONCLUSIVE", error="Temporary context may have been lost; inspect side effects before a new attempt")
                    self.reconcile(worker)
                    continue
                self.client.request("thread/resume", {"threadId": worker["id"], "excludeTurns": True})
                for task in self.store.rows("SELECT id FROM tasks WHERE worker=? AND state='DISPATCHING'", (worker["id"],)):
                    self.store.finish(task["id"], "INCONCLUSIVE", error="Dispatch acknowledgment lost; inspect native history before retry")
                self.reconcile(worker)
            except Exception as error:
                self.store.event("recovery_error", worker=worker["id"], payload={"error": str(error)[:1000]})

    def reconcile(self, worker):
        turns = self.turns(worker) if worker["kind"] != "temp" else []
        known = {r["turn"]: r for r in self.store.rows("SELECT * FROM tasks WHERE worker=? AND turn IS NOT NULL", (worker["id"],))}
        gone = False
        try:
            native = self.client.request("thread/read", {"threadId": worker["id"]})["thread"]
        except RpcError as error:
            if worker["kind"] != "temp" or not any(text in str(error).lower() for text in ("not loaded", "not found")):
                raise
            native, gone = {"status": {"type": "notLoaded"}}, True
        active = [turn["id"] for turn in turns if turn.get("status") == "inProgress"]
        active_turn = active[-1] if active else None
        if native.get("status", {}).get("type") == "active" and not active_turn:
            active_turn = worker["active_turn"] or "unknown"
        self.store.execute("UPDATE workers SET active_turn=? WHERE id=?", (active_turn, worker["id"]))
        for turn_id, task in known.items():
            if turn_id in self.completed:
                turns = [t for t in turns if t["id"] != turn_id] + [self.completed[turn_id]]
        for turn in turns:
            task = known.get(turn["id"])
            if task and turn.get("status") != "inProgress":
                outputs = [item for item in turn.get("items", []) if item.get("type") == "agentMessage"]
                final = [item for item in outputs if item.get("phase") == "final_answer"]
                result = "\n\n".join(item.get("text", "") for item in (final or outputs[-1:])).strip()
                status = turn.get("status")
                state = "CANCELLED" if status == "interrupted" else "FAILED" if status == "failed" else "READY" if result else "INCONCLUSIVE"
                if task["state"] not in TERMINAL:
                    self.store.finish(task["id"], state, result=result or None, error=json.dumps(turn.get("error")) if turn.get("error") else None)
                elif task["state"] in {"BLOCKED", "INCONCLUSIVE"} and result and result != task["result"]:
                    self.store.execute("UPDATE tasks SET result=?,updated=? WHERE id=?", (result, time.time(), task["id"]))
                    self.store.event("late_result", worker=worker["id"], task=task["id"], payload={"native_status": status}, key="late:" + task["id"])
                if worker["kind"] == "temp":
                    if not active_turn:
                        try:
                            self.background_clear(worker["id"], turn["id"])
                        except Exception:
                            pass  # Cleanup must obtain positive background evidence later.
                        self.store.execute("UPDATE workers SET mode='released' WHERE id=? AND mode NOT IN ('paused','manual')", (worker["id"],))
                        self.client.request("thread/unsubscribe", {"threadId": worker["id"]})
            elif not task and worker["id"] not in self.dispatching:
                # External inputs are synchronized, not presumed to grant new authority.
                if self.store.execute("INSERT OR IGNORE INTO events(worker,kind,payload,created,event_key) VALUES(?,?,?,?,?)",
                                      (worker["id"], "external_turn", json.dumps({"turn_id": turn["id"]}), time.time(), "external:" + turn["id"])):
                    self.store.execute("UPDATE workers SET mode='external' WHERE id=? AND mode='automatic'", (worker["id"],))
        if gone:
            for task in self.store.rows("SELECT id FROM tasks WHERE worker=? AND state IN ('QUEUED','RUNNING','DISPATCHING')", (worker["id"],)):
                self.store.finish(task["id"], "INCONCLUSIVE", error="Ephemeral thread is no longer loaded; inspect side effects before retry")

    def writers(self, include_reviews=False):
        rows = self.store.rows("SELECT DISTINCT w.* FROM workers w LEFT JOIN tasks t ON t.worker=w.id WHERE w.active_turn IS NOT NULL OR t.state IN ('RUNNING','DISPATCHING')")
        return rows if include_reviews else [w for w in rows if w["permission"] != "independent-review"]

    def idle_blockers(self):
        errors = []
        for worker in self.store.rows("SELECT * FROM workers WHERE mode!='released' OR active_turn IS NOT NULL"):
            try:
                self.reconcile(worker)
            except Exception as error:
                errors.append({"worker": worker["id"], "reason": "native state unknown: " + str(error)[:200]})
        blocked = self.store.rows("SELECT t.id,t.worker,t.router,t.state FROM tasks t JOIN workers w ON w.id=t.worker WHERE w.kind='temp' AND t.state IN ('QUEUED','RUNNING','DISPATCHING')")
        for worker in self.writers(include_reviews=True):
            if worker["active_turn"] and (worker["kind"] == "temp" or self.store.one(
                    "SELECT id FROM tasks WHERE worker=? AND state IN ('BLOCKED','INCONCLUSIVE') AND (turn=? OR turn IS NULL)", (worker["id"], worker["active_turn"]))):
                blocked.append({"worker": worker["id"], "router": worker["router"], "reason": "native turn still active", "turn": worker["active_turn"]})
        return blocked + errors

    def _dispatch(self, task):
        if self.draining:
            return False
        worker = self.store.worker(task["worker"])
        try:
            self.check_path(worker)
        except ValueError as error:
            self.store.finish(task["id"], "BLOCKED", error=str(error))
            return False
        if worker["mode"] != "automatic":
            return False
        if worker["permission"] != "independent-review" and self.write_blockers(worker["cwd"]):
            return False  # A takeover or a short Router microtask lease owns this worktree for now.
        if worker["permission"] != "independent-review" and any(
                w["id"] != worker["id"] and self.worker_overlap(w, worker) for w in self.writers()):
            return False
        try:
            view = self.sync(worker["id"], worker["router"])
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            if self.transient(error):
                return False
            self.store.finish(task["id"], "BLOCKED", error="Worker sync failed; inspect its environment: " + str(error)[:1000])
            return False
        if view.get("status", {}).get("type") == "active":
            return False
        if view["sync_token"] != task["baseline"]:
            self.store.finish(task["id"], "BLOCKED", error="Project or external inputs changed while queued; Router must sync and issue a revised task")
            return False
        self.store.execute("UPDATE tasks SET state='DISPATCHING',updated=? WHERE id=? AND state='QUEUED'", (time.time(), task["id"]))
        text = ("[CCW task " + task["id"] + "]\ninvocation: delegated\nAuthorization: " + task["authorization"] +
                "\nShared project authority: " + view["project_root"] + ". Execution cwd: " + worker["cwd"] +
                ". Read current project AGENTS.md (or existing CLAUDE.md when no AGENTS.md exists) and relevant shared state there before acting. Do not replace central facts with a stale checkout copy. Indexed knowledge: " + ", ".join(view["project_knowledge"]) + ". Use available skills only when needed.\n" + task["prompt"] +
                "\nReturn concrete artifacts, observed checks, unresolved assumptions, shared project changes and any direct human corrections. Do not call Claude again; this task is already delegated.")
        text += "\nWrite only your assigned files/outputs; serialize Git index/branch changes and shared status integration. Managed .claude/cc-codex-super-agent/worktrees belong only to their assigned temp; do not write or recursively modify them from the main checkout."
        if view["_takeover_history"]:
            text += "\nRecent Router direct work (Claude takeover, separate from Codex turns and acceptance):\n" + json.dumps(view["_takeover_history"][-20:], ensure_ascii=False)
        self.dispatching.add(worker["id"])
        try:
            response = self.client.request("turn/start", {"threadId": worker["id"], "input": [{"type": "text", "text": text}],
                                                         "model": task["model"], "effort": task["effort"], "approvalPolicy": "never"})
            started = time.time()
            budget = task["run_seconds"] or max(60, task["deadline"] - task["created"])
            self.store.execute("UPDATE tasks SET state='RUNNING',turn=?,updated=?,started=?,deadline=? WHERE id=?", (response["turn"]["id"], started, started, started + budget, task["id"]))
            self.store.execute("UPDATE workers SET active_turn=? WHERE id=?", (response["turn"]["id"], worker["id"]))
        except Exception as error:
            # A timeout may follow a successful native action; never blindly retry.
            self.store.finish(task["id"], "INCONCLUSIVE", error="Dispatch uncertain: " + str(error))
            self.store.execute("UPDATE workers SET active_turn=COALESCE(active_turn,'unknown') WHERE id=?", (worker["id"],))
        finally:
            self.dispatching.discard(worker["id"])
        return True

    def _schedule_once(self):
        with self.lock:
            if self.draining:
                return
            for worker in self.store.rows("SELECT * FROM workers WHERE mode!='released' OR active_turn IS NOT NULL"):
                try:
                    self.reconcile(worker)
                except Exception as error:
                    self.store.event("worker_reconcile_error", worker=worker["id"], payload={"error": str(error)[:500]},
                                     key="reconcile-error:" + worker["id"] + ":" + digest(str(error)) + ":" + str(int(time.time() / 60)))
                    if self.transient(error):
                        continue
                    for queued in self.store.rows("SELECT id FROM tasks WHERE worker=? AND state='QUEUED'", (worker["id"],)):
                        self.store.finish(queued["id"], "BLOCKED", error="Native state unavailable; inspect before retry")
            active = len(self.writers(include_reviews=True))
            for task in self.store.rows("SELECT * FROM tasks WHERE state IN ('QUEUED','RUNNING') ORDER BY created"):
                if task["state"] == "QUEUED" and (task["queue_deadline"] or task["deadline"]) < time.time():
                    self.store.finish(task["id"], "BLOCKED", error="Queue deadline reached before dispatch; no native turn was started")
                elif task["state"] == "RUNNING" and task["deadline"] < time.time():
                    self.store.finish(task["id"], "BLOCKED", error="Deadline reached; active native turn was preserved for explicit inspection/cancel")
                elif task["state"] == "QUEUED" and active < 2:
                    # Only a task that actually started counts against the cap; a task waiting
                    # on its own worktree writer must not starve unrelated projects.
                    try:
                        if self._dispatch(task):
                            active += 1
                    except Exception as error:
                        if self.transient(error):
                            continue
                        self.store.finish(task["id"], "BLOCKED", error="Task environment unavailable: " + str(error)[:1000])
            if not self.writers(include_reviews=True) and time.monotonic() - self.last_cleanup >= 30:
                self.last_cleanup = time.monotonic()
                resource = self.store.one("""SELECT s.* FROM workspaces s JOIN workers w ON w.id=s.worker
                    WHERE s.state='IN_USE' AND w.mode='released'
                    AND EXISTS(SELECT 1 FROM tasks t WHERE t.worker=w.id)
                    AND NOT EXISTS(SELECT 1 FROM tasks t WHERE t.worker=w.id AND t.state!='ACCEPTED')
                    ORDER BY coalesce((SELECT cast(value AS REAL) FROM meta WHERE key='cleanup-at:'||s.id),0),s.created LIMIT 1""")
                if resource:
                    self.store.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                       ("cleanup-at:" + resource["id"], str(time.time())))
                    try:
                        self.workspace(resource["router"], resource["id"], cleanup=True)
                    except Exception as error:
                        self.store.event("workspace_cleanup_deferred", worker=resource["worker"], payload={"resource": resource["id"], "reason": str(error)[:500]},
                                         key="cleanup-deferred:" + resource["id"] + ":" + digest(str(error)) + ":" + str(int(time.time() / 3600)))

    def _schedule(self):
        while not self.stopped.wait(1):
            try:
                if self.client.closed:
                    self.client = NativeClient(self.native_socket, self.on_event)
                    self.recover()
                self._schedule_once()
            except Exception as error:
                self.store.event("scheduler_error", payload={"error": str(error)[:1200]})
                self.stopped.wait(3)

    def control(self, worker_id, router, mode=None, pinned=None):
        worker = self.owned(worker_id, router)
        if mode is None and pinned is None:
            raise ValueError("Choose a control mode or pin preference")
        if mode is not None and mode not in {"automatic", "paused", "manual", "released"}:
            raise ValueError("Unknown control mode")
        if pinned is not None and type(pinned) is not bool:
            raise ValueError("Pin preference must be boolean")
        if pinned is not None and worker["kind"] == "temp":
            raise ValueError("Temporary Workers cannot be pinned")
        if mode == "released" and (worker["active_turn"] or self.store.one("SELECT id FROM tasks WHERE worker=? AND state IN ('QUEUED','DISPATCHING','RUNNING')", (worker_id,))):
            raise ValueError("Finish/cancel pending tasks before releasing control")
        self.store.execute("UPDATE workers SET mode=?,pinned=?,updated=? WHERE id=?",
                           (mode or worker["mode"], worker["pinned"] if pinned is None else int(pinned), time.time(), worker_id))
        self.store.event("control", worker=worker_id, payload={"mode": mode or worker["mode"], "router": router, "pinned": bool(worker["pinned"] if pinned is None else pinned)})
        return self.store.worker(worker_id)

    def cancel(self, task_id, router):
        task = self.store.task(task_id)
        worker = self.owned(task["worker"], router)
        active_terminal = bool(task["state"] in TERMINAL and task["turn"] and worker["active_turn"] == task["turn"])
        if task["state"] in TERMINAL and not active_terminal:
            return task
        if task["turn"]:
            view = self.client.request("thread/read", {"threadId": task["worker"]})["thread"]
            turns = self.turns(self.store.worker(task["worker"]))
            active = [t["id"] for t in turns if t.get("status") == "inProgress"]
            if task["turn"] not in active and worker["active_turn"] != task["turn"] and view.get("status", {}).get("type") == "active":
                raise ValueError("Another native turn is active; do not interrupt the human's turn")
            self.client.request("turn/interrupt", {"threadId": task["worker"], "turnId": task["turn"]})
        if active_terminal:
            self.store.execute("UPDATE tasks SET state='CANCELLED',error=?,updated=? WHERE id=?", ("Cancelled by assigned Router", time.time(), task_id))
            self.store.event("cancelled_after_terminal", worker=worker["id"], task=task_id, payload={"previous_state": task["state"]})
        else:
            self.store.finish(task_id, "CANCELLED", error="Cancelled by assigned Router")
        self.store.execute("UPDATE workers SET active_turn=NULL WHERE id=? AND active_turn=?", (worker["id"], task["turn"]))
        if self.store.worker(task["worker"])["kind"] == "temp":
            try:
                self.background_clear(task["worker"], task["turn"] or "unused")
            except Exception:
                pass
            self.client.request("thread/unsubscribe", {"threadId": task["worker"]})
            self.store.execute("UPDATE workers SET mode='released' WHERE id=?", (task["worker"],))
        return self.store.task(task_id)

    def steer(self, worker_id, router, expected_turn, prompt, authorization):
        self.owned(worker_id, router)
        if not prompt.strip() or not authorization.strip():
            raise ValueError("Immediate correction needs its concrete instruction and authorization")
        turns = self.turns(self.store.worker(worker_id))
        if expected_turn not in {t["id"] for t in turns if t.get("status") == "inProgress"}:
            raise ValueError("Expected active turn changed; sync instead of steering a different turn")
        response = self.client.request("turn/steer", {"threadId": worker_id, "expectedTurnId": expected_turn,
                                                     "input": [{"type": "text", "text": "Authorized immediate correction (" + authorization + "): " + prompt}]})
        self.store.event("steer", worker=worker_id, payload={"turn_id": expected_turn, "authorization": authorization})
        return response

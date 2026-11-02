"""Programmatic Claude hooks: short context, role guard and bounded wakeup."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

from . import __version__
from .paths import worktree_root
from .service import call, state_root
from .store import Store


def title(data):
    path = Path(data.get("transcript_path", "/nonexistent"))
    if path.is_file():
        with path.open("rb") as f:
            f.seek(max(0, path.stat().st_size - 256 * 1024))
            lines = f.read().decode("utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            try:
                item = json.loads(line)
                if item.get("type") == "custom-title" and item.get("customTitle"):
                    return item["customTitle"]
            except (ValueError, TypeError):
                continue
    return Path(data.get("cwd", os.getcwd())).name or "Router"


def project_entry(data):
    """Prefer Claude's stable launch identity; Bash cd must not move the team."""
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return os.environ["CLAUDE_PROJECT_DIR"]
    path = Path(data.get("transcript_path", "/nonexistent"))
    if path.is_file():
        with path.open("rb") as f:
            for line in f.read(256 * 1024).decode("utf-8", errors="ignore").splitlines():
                try:
                    item = json.loads(line)
                    if item.get("cwd") and Path(item["cwd"]).is_dir():
                        return item["cwd"]
                except (ValueError, TypeError):
                    continue
    return data.get("cwd", os.getcwd())


def context(data, start=False):
    router = data["session_id"]
    name = title(data)
    # UserPromptSubmit also covers sessions that predate installation or missed start.
    registration = call("router", {"router": router, "name": name, "cwd": project_entry(data)})
    project = (registration or {}).get("project_root", project_entry(data))
    if start:
        env = os.environ.get("CLAUDE_ENV_FILE")
        if env:
            with Path(env).open("a") as f:
                f.write("\nexport CCW_ROUTER_ID=" + shlex.quote(router) + "\n")
                f.write("export CCW_ROUTER_NAME=" + shlex.quote(name) + "\n")
                f.write("export CCW_PROJECT_ROOT=" + shlex.quote(project) + "\n")
    workers = call("list", {"router": router, "limit": 10})
    inbox = call("inbox", {"router": router})
    text = (f"Claude/Codex Workflow {__version__}: you are the Router; stable ID {router}. "
            "Use /claude-codex-router for substantive delegated work. Direct low-risk microtasks remain allowed. "
            "Use ai-work, not codex exec or extra Claude nested sessions. Project facts live in shared project files. "
            ""
            "Personally perform requested Claude review/design/refinement; use scoped takeover for explicitly authorized substantive writes. "
            "Retain idle formal Workers and search your roster before creating a new one. "
            "Always sync a continuing Worker before following up. No extra Claude teams or public publication are authorized by this hook.")
    text += ("\nStable project entry: " + project + ". Your formal Workers must use this exact cwd. "
             "Create temp worktrees only with ai-work open --kind temp --isolation worktree. "
             "Subprojects get a separate Router only when the user starts one there. "
             "User-named external sessions retain their path/owner: inspect first, adopt only for explicit takeover. "
             "Declare file/output responsibilities; queue overlapping writes or use an isolated temp.")
    if workers:
        text += "\nYour Workers (priority summary; use ai-work list --query to find others): " + "; ".join(w["name"] + "=" + w["id"] + " (" + w["mode"] + ("; needs path repair" if w.get("needs_repair") else "") + ")" for w in workers)
    if inbox:
        text += "\nPending review: " + ", ".join(t["id"] + ":" + t["state"] for t in inbox[:8]) + ". Read ai-work inbox/result; inspect evidence, then accept/reject."
    for takeover in call("takeover", {"router": router, "status": True})["takeovers"]:
        text += ("\nActive takeover: " + ", ".join(takeover["scope"]) + f"; {takeover['remaining_seconds'] / 60:.0f} min remaining. "
                 "结束前把变更、证据、待复核项写进共享项目文档；Codex 恢复后可派独立复核。")
    event = "SessionStart" if start else "UserPromptSubmit"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}, ensure_ascii=False))
    return 0


def guard(data):
    router = data["session_id"]
    tool = data.get("tool_name", "")
    inputs = data.get("tool_input", {})
    reason = None
    if tool in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        raw = inputs.get("file_path") or inputs.get("notebook_path") or inputs.get("path")
        if raw:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = Path(data.get("cwd", os.getcwd())) / path
            path = path.resolve()
            # Router planning, feedback, skill/rule editing and final prose are its job.
            # Directory names count only inside the file's own project, not in its ancestors.
            base = worktree_root(path) or Path(data.get("cwd", os.getcwd())).resolve()
            inside = path.relative_to(base).parts[:-1] if path.is_relative_to(base) else ()
            allowed = path.suffix.lower() in {".md", ".txt", ".rst"} or any(p in inside for p in ["docs", "templates", "rules"])
            if not allowed and (state_root() / "state.sqlite3").exists():
                try:
                    with Store(state_root()) as store:
                        allowed = bool(store.one("SELECT path FROM leases WHERE router=? AND path=? AND expires>?", (router, str(path), time.time())))
                        if not allowed:
                            allowed = any(path.is_relative_to(Path(scope)) for takeover in store.active_takeovers(router) for scope in takeover["scope"])
                except Exception as error:
                    # Fail closed only for the governed write itself; other tools and prose stay usable.
                    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                      "permissionDecisionReason": "Coordinator state is unreadable, so this code write cannot be checked against Worker writes (" + str(error)[:200] + "). Run ai-work doctor, then retry."}}))
                    return 0
            if not allowed:
                reason = "Delegate routine substantive implementation. If the user explicitly assigned Claude this design/refinement/implementation, use ai-work takeover with the authorized scope and reason; no quota failure is required. For a low-risk reversible microtask, use ai-work direct naming the exact file, reason and immediate verification."
    elif tool == "Bash":
        command = inputs.get("command", "")
        if re.search(r"\bcodex\s+(?:exec|review)\b", command) or re.search(r"\bclaude\s+(?:--bg|--background)\b", command):
            reason = "The old one-shot/nested invocation path is retired. Use /claude-codex-router and ai-work with an explicit persistent or temporary lifecycle."
    if reason:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))
    return 0


def watch(data):
    root = state_root()
    if not (root / "state.sqlite3").is_file():
        return 0
    router = data["session_id"]
    lock = root / ("watch-" + hashlib.sha256(router.encode()).hexdigest()[:16] + ".lock")
    with lock.open("a+") as f:
        os.chmod(lock, 0o600)
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        with Store(root) as store:
            end = time.monotonic() + min(int(os.environ.get("CCW_WATCH_SECONDS", "2700")), 2700)
            while True:
                ready = store.rows("SELECT t.id,t.worker,t.state FROM tasks t JOIN workers w ON w.id=t.worker WHERE t.router=? AND t.state IN ('READY','FAILED','BLOCKED','INCONCLUSIVE') AND t.notified IS NULL AND w.mode NOT IN ('paused','manual') AND (w.mode!='released' OR w.kind='temp')", (router,))
                if ready:
                    for task in ready:
                        store.execute("UPDATE tasks SET notified=? WHERE id=? AND notified IS NULL", (time.time(), task["id"]))
                    print("Codex results need Router review: " + ", ".join(t["id"] + " (" + t["state"] + ")" for t in ready) + ". Read ai-work inbox/result, sync any direct human input and shared project changes, then review. This is a completion notification; do not replay the work or assume acceptance.", file=sys.stderr)
                    return 2  # Claude's documented asyncRewake protocol.
                pending = store.one("SELECT t.id FROM tasks t JOIN workers w ON w.id=t.worker WHERE t.router=? AND t.state IN ('QUEUED','DISPATCHING','RUNNING') AND w.mode NOT IN ('paused','manual','released')", (router,))
                if not pending or time.monotonic() >= end:
                    return 0
                time.sleep(.5)


def run(event):
    try:
        data = json.load(sys.stdin)
        if not data.get("session_id"):
            raise ValueError("Claude hook did not provide a session ID")
        if event == "start":
            return context(data, start=True)
        if event == "context":
            return context(data)
        if event == "guard":
            return guard(data)
        return watch(data)
    except Exception as error:
        # An unavailable integration must not destroy an unrelated user conversation.
        # No delegation is attempted; native task results remain in the private queue.
        print("CCW hook needs attention: " + str(error), file=sys.stderr)
        return 0

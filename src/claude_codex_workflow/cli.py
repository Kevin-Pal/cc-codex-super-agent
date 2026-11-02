"""Small, validated CLI. Always prints JSON for coordination operations."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .service import call, restart_daemon, serve
from .store import TERMINAL


def parser():
    p = argparse.ArgumentParser(prog="ai-work")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    daemon = sub.add_parser("daemon")
    action = daemon.add_mutually_exclusive_group()
    action.add_argument("--stop", action="store_true")
    action.add_argument("--restart", action="store_true")
    daemon.add_argument("--when-idle", action="store_true")
    daemon.add_argument("--timeout", type=float, default=300)
    for name in ["open", "sync", "send", "adopt", "list", "result", "inbox", "review", "cancel", "control", "events", "direct", "router", "steer", "takeover"]:
        c = sub.add_parser(name)
        c.add_argument("--router", default=os.environ.get("CCW_ROUTER_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID"))
        if name in {"open", "adopt", "router"}:
            c.add_argument("--router-name", default=os.environ.get("CCW_ROUTER_NAME") or "Router")
        if name in {"open", "router"}:
            c.add_argument("--cwd", default=os.getcwd())
        if name == "open":
            c.add_argument("--direction", required=True)
            c.add_argument("--stream")
            c.add_argument("--kind", choices=["worker", "temp"], default="worker")
            c.add_argument("--tier", choices=["easy", "hard", "xhard"], default="hard")
            c.add_argument("--permission", choices=["trusted-worker", "independent-review"], default="trusted-worker")
        if name in {"sync", "send", "control", "steer"}:
            c.add_argument("worker_id")
        if name == "sync":
            c.add_argument("--history", action="store_true")
        if name == "adopt":
            c.add_argument("thread_id")
            c.add_argument("--from-router")
        if name in {"send", "steer"}:
            source = c.add_mutually_exclusive_group(required=True)
            source.add_argument("--text")
            source.add_argument("--file", type=Path)
            c.add_argument("--authorization", required=True)
        if name == "steer":
            c.add_argument("--expected-turn", required=True)
        if name == "send":
            c.add_argument("--sync-token")
            c.add_argument("--key")
            c.add_argument("--tier", choices=["easy", "hard", "xhard"])
            c.add_argument("--minutes", type=int, default=45)
            c.add_argument("--queue-minutes", type=int, default=45)
        if name in {"result", "review", "cancel"}:
            c.add_argument("task_id")
        if name == "result":
            c.add_argument("--wait", type=int, default=0)
        if name == "review":
            c.add_argument("--verdict", choices=["accept", "reject"], required=True)
            c.add_argument("--note", required=True)
        if name == "control":
            c.add_argument("mode", nargs="?", choices=["automatic", "manual", "paused", "released"])
            preference = c.add_mutually_exclusive_group()
            preference.add_argument("--pin", dest="pinned", action="store_true", default=None)
            preference.add_argument("--unpin", dest="pinned", action="store_false")
        if name == "list":
            c.add_argument("--query")
            c.add_argument("--limit", type=int)
            c.add_argument("--all", dest="include_released", action="store_true")
        if name == "events":
            c.add_argument("--after", type=int, default=0)
        if name == "direct":
            c.add_argument("paths", nargs="+")
            c.add_argument("--reason", required=True)
            c.add_argument("--seconds", type=int, default=300)
        if name == "takeover":
            mode = c.add_mutually_exclusive_group(required=True)
            mode.add_argument("--scope", action="append")
            mode.add_argument("--release", action="store_true")
            mode.add_argument("--status", action="store_true")
            c.add_argument("--reason")
            c.add_argument("--hours", type=float, default=2)
            c.add_argument("--note")
    c = sub.add_parser("hook")
    c.add_argument("event", choices=["start", "context", "guard", "watch"])
    c = sub.add_parser("install")
    c.add_argument("--home", type=Path, default=Path.home())
    c.add_argument("--role", choices=["router", "worker", "both"], default="both")
    c.add_argument("--apply", action="store_true")
    c = sub.add_parser("uninstall")
    c.add_argument("--home", type=Path, default=Path.home())
    c.add_argument("--apply", action="store_true")
    return p


def main(argv=None):
    a = vars(parser().parse_args(argv))
    command = a.pop("command")
    try:
        if command == "daemon":
            if a["restart"]:
                if not a["when_idle"]:
                    raise ValueError("Daemon restart requires --when-idle")
                print(json.dumps({"ok": True, "result": restart_daemon(timeout=a["timeout"])}))
            elif a["when_idle"]:
                raise ValueError("--when-idle requires --restart")
            elif a["stop"]:
                print(json.dumps({"ok": True, "result": call("shutdown", autostart=False)}))
            else:
                serve()
            return 0
        if command == "hook":
            from .hooks import run
            return run(a["event"])
        if command in {"install", "uninstall"}:
            from .install import install, uninstall
            result = install(**a) if command == "install" else uninstall(**a)
        else:
            if command != "doctor" and not a.get("router"):
                raise ValueError("Router ID missing: use --router, CCW_ROUTER_ID or CLAUDE_CODE_SESSION_ID")
            if command in {"send", "steer"}:
                path = a.pop("file")
                a["prompt"] = path.read_text() if path else a.pop("text")
                a.pop("text", None)
            elif command == "router":
                a["name"] = a.pop("router_name")
            elif command == "review":
                a["accepted"] = a.pop("verdict") == "accept"
            wait = a.pop("wait", 0)
            if wait < 0 or wait > 3600:
                raise ValueError("Wait must be 0..3600 seconds")
            end = time.monotonic() + wait
            while True:
                result = call(command, a)
                if not wait or result["state"] in TERMINAL or time.monotonic() >= end:
                    break
                time.sleep(.5)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())

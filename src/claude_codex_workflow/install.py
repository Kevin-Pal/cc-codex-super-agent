"""Versioned, reversible user installation; never manages API/provider fields."""
from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .service import peek_runtime

START = "<!-- claude-codex-workflow:begin -->"
END = "<!-- claude-codex-workflow:end -->"

SHARED = (Path(__file__).resolve().parents[2] / "rules/entries/shared.md").read_text()

COMMON = (Path(__file__).resolve().parents[2] / "rules/entries/project-policy.md").read_text()


def block(text, content):
    text = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\s*", "", text, flags=re.S).rstrip()
    return text + "\n\n" + START + "\n" + content.rstrip() + "\n" + END + "\n"


def entry(role):
    filename = "claude-router.md" if role == "router" else "codex-worker.md"
    return (Path(__file__).resolve().parents[2] / "rules/entries" / filename).read_text()


def snapshot(path):
    if path.is_symlink():
        return {"kind": "symlink", "target": os.readlink(path)}
    if not path.exists():
        return {"kind": "missing"}
    if not path.is_file():
        raise ValueError("Refuse to replace an unmanaged directory: " + str(path))
    s = path.stat()
    return {"kind": "file", "data": base64.b64encode(path.read_bytes()).decode(),
            "mode": stat.S_IMODE(s.st_mode), "uid": s.st_uid, "gid": s.st_gid}


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    os.close(fd)
    p = Path(temporary)
    try:
        if value["kind"] == "symlink":
            p.unlink()
            p.symlink_to(value["target"])
        elif value["kind"] == "file":
            p.write_bytes(base64.b64decode(value["data"]))
            os.chmod(p, value.get("mode", 0o644))
            if "uid" in value:
                os.chown(p, value["uid"], value["gid"])
        else:
            path.unlink(missing_ok=True)
            return
        os.replace(p, path)
    finally:
        p.unlink(missing_ok=True)


def file_value(text, mode=0o644, previous=None):
    value = {"kind": "file", "data": base64.b64encode(text.encode()).decode(), "mode": mode, "uid": os.getuid(), "gid": os.getgid()}
    if previous and previous["kind"] == "file":
        value.update({k: previous[k] for k in ["mode", "uid", "gid"]})
    return value


def owned_hook(command):
    return "ai-work hook " in command


def install(home=Path.home(), role="both", apply=False):
    home = Path(home).expanduser().resolve()
    source = Path(__file__).resolve().parents[2]
    required = [p for folder in ["src", "skills", "docs", "rules", "templates"] for p in (source / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    required += [source / "pyproject.toml"]
    stamp = hashlib.sha256(b"".join(str(p.relative_to(source)).encode() + b"\0" + p.read_bytes() for p in sorted(required))).hexdigest()[:12]
    base = home / ".local/share/claude-codex-workflow"
    release = base / "releases" / (__version__ + "-" + stamp)
    current = base / "current"
    changes = {}

    def put(path, text, mode=0o644):
        before = snapshot(path)
        changes[str(path)] = {"before": before, "after": file_value(text, mode, before)}

    def link(path, target):
        before = snapshot(path)
        if before["kind"] != "missing" and not (before["kind"] == "symlink" and "claude-codex-workflow" in before["target"]):
            raise ValueError("Existing skill/entry is not owned by this package: " + str(path))
        changes[str(path)] = {"before": before, "after": {"kind": "symlink", "target": str(target)}}

    link(current, release)
    launcher = "#!/bin/sh\nCCW_SOURCE=" + shlex.quote(str(current / "src")) + '\nexport PYTHONPATH="$CCW_SOURCE${PYTHONPATH:+:$PYTHONPATH}"\nexec ' + shlex.quote(sys.executable) + ' -m claude_codex_workflow.cli "$@"\n'
    binary = home / ".local/bin/ai-work"
    if binary.exists() and "claude_codex_workflow.cli" not in binary.read_text():
        raise ValueError("ai-work is already owned by another program")
    put(binary, launcher, 0o755)
    managed_sources = (home / ".agents/global/shared.md").is_file() and (home / ".agents/global/codex.md").is_file() and (home / ".local/bin/agents-sync").is_file()
    if role in {"router", "both"}:
        claude = home / ".claude/CLAUDE.md"
        text = claude.read_text() if claude.exists() else ""
        put(claude, block(text, entry("router")))
        link(home / ".claude/skills/claude-codex-router", current / "skills/claude-codex-router")
        settings = home / ".claude/settings.json"
        data = json.loads(settings.read_text()) if settings.exists() else {}
        hooks = data.setdefault("hooks", {})
        for event, rows in list(hooks.items()):
            preserved = []
            for row in rows:
                remaining = [h for h in row.get("hooks", []) if not owned_hook(h.get("command", ""))]
                if remaining:
                    preserved.append({**row, "hooks": remaining})
            hooks[event] = preserved
        command = shlex.quote(str(binary))
        specifications = {
            "SessionStart": (None, "start", False),
            "UserPromptSubmit": (None, "context", False),
            "PreToolUse": ("Write|Edit|MultiEdit|NotebookEdit|Bash", "guard", False),
            "PostToolUse": ("Bash", "watch", True),
            "Stop": (None, "watch", True),
        }
        for event, (matcher, action, background) in specifications.items():
            hook = {"type": "command", "command": command + " hook " + action, "timeout": 3000 if background else 20}
            if background:
                hook["asyncRewake"] = True
            row = {"hooks": [hook]}
            if matcher:
                row["matcher"] = matcher
            hooks.setdefault(event, []).append(row)
        put(settings, json.dumps(data, ensure_ascii=False, indent=2) + "\n", 0o600)
    if role in {"worker", "both"}:
        link(home / ".agents/skills/claude-codex-worker", current / "skills/claude-codex-worker")
        if managed_sources:
            shared = home / ".agents/global/shared.md"
            put(shared, block(shared.read_text(), SHARED + "\n\n" + COMMON))
            codex = home / ".agents/global/codex.md"
            put(codex, block(codex.read_text(), entry("worker")))
        else:
            target = home / ".codex/AGENTS.md"
            text = target.read_text() if target.exists() else ""
            put(target, block(text, entry("worker")))
    changes = {p: record for p, record in changes.items() if record["before"] != record["after"]}
    result = {"version": __version__, "release": str(release), "role": role, "apply": apply,
              "changed_paths": list(changes), "provider_fields_modified": [], "restart_existing_sessions": False,
              "recommended_next_step": "Save work, exit the one active Claude process, then claude --resume <session-id>; no second concurrent resume. Run ai-work doctor."}
    if not apply:
        return result
    daemon = peek_runtime(home)
    restart_needed = bool(daemon and daemon.get("daemon_release") != str(release))
    result.update(daemon_restart_needed=restart_needed, running_daemon=daemon,
                  recommended_daemon_command="ai-work daemon --restart --when-idle --timeout 300" if restart_needed else None)
    if restart_needed:
        result["recommended_next_step"] += " The running coordinator still uses an older or unidentified release; use the recommended idle restart command."
        if not daemon.get("atomic_idle_restart"):
            result["daemon_restart_note"] = "The old daemon lacks atomic idle-restart support. Automatic stop is refused; arrange a coordinated first upgrade."
    if not changes:
        result["unchanged"] = True
        return result
    # Preflight every target before touching any of them.
    for path, record in changes.items():
        if snapshot(Path(path)) != record["before"]:
            raise ValueError("Concurrent installation target changed: " + path)
    if not release.exists():
        release.mkdir(parents=True, mode=0o755)
        for p in required:
            target = release / p.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            if p.is_symlink() and p.suffix == ".md":
                # Reference copies are generated from one canonical source. Their
                # inner links must still resolve after materializing a symlink.
                def relocated(match):
                    raw = match[1]
                    if "://" in raw or raw.startswith("#"):
                        return match[0]
                    path, separator, anchor = raw.partition("#")
                    canonical = (p.resolve().parent / path).resolve()
                    if not canonical.is_relative_to(source) or not canonical.exists():
                        raise ValueError("Invalid skill reference target: " + raw)
                    return "](" + str(release / canonical.relative_to(source)) + ("#" + anchor if separator else "") + ")"
                target.write_text(re.sub(r"\]\(([^)]+)\)", relocated, p.read_text()))
    state = home / ".local/state/claude-codex-workflow"
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    backup = Path(tempfile.mkdtemp(prefix="install-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-", dir=state))
    os.chmod(backup, 0o700)
    # Save the generated output too; restore only against an exact after snapshot.
    generated = home / ".codex/AGENTS.md"
    generated_before = snapshot(generated) if managed_sources and role in {"worker", "both"} else None
    pointer = state / "installed.json"
    manifest = {"version": __version__, "release": str(release), "paths": changes, "generated_before": generated_before, "home": str(home), "installed_pointer_before": snapshot(pointer)}
    manifest_path = backup / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    os.chmod(manifest_path, 0o600)
    for path, record in changes.items():
        if snapshot(Path(path)) != record["before"]:
            raise ValueError("Concurrent installation target changed: " + path)
        atomic(Path(path), record["after"])
    if managed_sources and role in {"worker", "both"}:
        subprocess.run([str(home / ".local/bin/agents-sync")], env={**os.environ, "AGENTS_SYNC_HOME": str(home)}, check=True, capture_output=True)
        manifest["generated_after"] = snapshot(generated)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    pointer.write_text(json.dumps({"manifest": str(manifest_path), "release": str(release), "version": __version__}) + "\n")
    os.chmod(pointer, 0o600)
    result["backup"] = str(backup)
    return result


def uninstall(home=Path.home(), apply=False):
    home = Path(home).expanduser().resolve()
    pointer = home / ".local/state/claude-codex-workflow/installed.json"
    manifest = json.loads(Path(json.loads(pointer.read_text())["manifest"]).read_text())
    for path, record in manifest["paths"].items():
        if snapshot(Path(path)) != record["after"]:
            raise ValueError("Installed file changed later; merge manually instead of overwriting: " + path)
    generated = home / ".codex/AGENTS.md"
    if manifest.get("generated_after") and snapshot(generated) != manifest["generated_after"]:
        raise ValueError("Generated instructions changed since install; preserve and reconcile their source")
    result = {"apply": apply, "restore_paths": list(manifest["paths"]), "sessions_deleted": False}
    if apply:
        for path, record in reversed(list(manifest["paths"].items())):
            atomic(Path(path), record["before"])
        if manifest.get("generated_before"):
            atomic(generated, manifest["generated_before"])
        atomic(pointer, manifest.get("installed_pointer_before", {"kind": "missing"}))
    return result

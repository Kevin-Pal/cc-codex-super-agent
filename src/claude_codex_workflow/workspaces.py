"""Owned temporary checkouts. No native session or project identity lives here."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .paths import worktree_root


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True,
                                   stderr=subprocess.PIPE, timeout=30).strip()


def namespace(project):
    path = Path(project) / ".claude/cc-codex-super-agent"
    if path.resolve() != path:
        raise ValueError("Project resource namespace must not contain symlinks")
    return path


def prepare(store, router, project, repo=None, base=None):
    project = Path(project).resolve(strict=True)
    selected = Path(repo or project).expanduser().resolve(strict=True)
    if not selected.is_relative_to(project):
        raise ValueError("A temp repository must belong to the Router project")
    root = worktree_root(selected)
    if root is None:
        raise ValueError("Worktree isolation requires a Git repository")
    if selected != root and selected != project:
        raise ValueError("Select an actual repository root, not an arbitrary execution directory")
    area = namespace(project)
    area.mkdir(parents=True, exist_ok=True, mode=0o700)
    area.chmod(0o700)
    common = Path(git(root, "rev-parse", "--git-common-dir"))
    common = (root / common).resolve()
    outer = worktree_root(project)
    exclude_root = outer if outer and area.is_relative_to(outer) else root
    exclude_common = (exclude_root / git(exclude_root, "rev-parse", "--git-common-dir")).resolve()
    exclude = exclude_common / "info/exclude"
    pattern = "/" + area.relative_to(exclude_root).as_posix() + "/" if area.is_relative_to(exclude_root) else None
    # Local exclusion only; never replace the user's tracked .gitignore.
    old = exclude.read_text() if exclude.exists() else ""
    if pattern and pattern not in old.splitlines():
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a") as f:
            f.write("\n# cc-codex-super-agent project resources\n" + pattern + "\n")
    dirty = bool(git(root, "status", "--porcelain", "--untracked-files=normal"))
    if dirty and base is None:
        raise ValueError("Source checkout has changes; choose an explicit committed --base (no stash/copy is automatic)")
    revision = git(root, "rev-parse", "--verify", "--end-of-options", (base or "HEAD") + "^{commit}")
    key = hashlib.sha256(str(common).encode()).hexdigest()[:12]
    resource = str(uuid.uuid4())
    path = area / "worktrees" / key / resource
    if path.resolve() != path:
        raise ValueError("Managed worktree parent must not contain symlinks")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    branch = "ccw/temp-" + resource
    store.execute("INSERT INTO workspaces VALUES(?,?,?,?,?,?,?,?,NULL,?)",
                  (resource, router, str(project), str(root), str(path), branch, revision, "PREPARING", time.time()))
    # Record first: failed/uncertain preparation is inspectable, never blindly retried.
    git(root, "worktree", "add", "-b", branch, str(path), revision)
    store.execute("UPDATE workspaces SET state='PREPARED' WHERE id=?", (resource,))
    manifest = area / "receipts" / (resource + ".json")
    manifest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest.write_text(json.dumps({"id": resource, "project_root": str(project), "repo": str(root),
                                    "path": str(path), "branch": branch, "base": revision,
                                    "dirty_source": dirty}, indent=2) + "\n")
    manifest.chmod(0o600)
    execution = path / selected.relative_to(root)
    if not execution.is_dir():
        raise ValueError("Selected project directory is absent from the committed base; prepared resource retained")
    return resource, str(execution)


def verified(row):
    path = Path(row["path"])
    area = namespace(Path(row["project_root"]))
    if not path.is_relative_to(area / "worktrees") or path.resolve() != path:
        raise ValueError("Worktree ownership path changed")
    if worktree_root(path) != path:
        raise ValueError("Managed checkout is missing or its Git root changed")
    common = (path / git(path, "rev-parse", "--git-common-dir")).resolve()
    expected = (Path(row["repo"]) / git(row["repo"], "rev-parse", "--git-common-dir")).resolve()
    if common != expected or git(path, "symbolic-ref", "--short", "HEAD") != row["branch"]:
        raise ValueError("Worktree repository or branch identity changed")
    return path


def remove(store, row):
    path = verified(row)
    busy = users_of(path)
    if busy:
        raise ValueError("Worktree still has processes/open files: " + str(busy[:8]))
    if git(path, "status", "--porcelain", "--untracked-files=all", "--ignored"):
        raise ValueError("Worktree has tracked, untracked or ignored changes; preserve/integrate artifacts first")
    head = git(path, "rev-parse", "HEAD")
    if head != row["base"]:
        result = subprocess.run(["git", "-C", row["repo"], "merge-base", "--is-ancestor", head, "HEAD"],
                                capture_output=True, timeout=10)
        if result.returncode:
            raise ValueError("Worktree commits are not integrated into the source checkout")
    git(row["repo"], "worktree", "remove", str(path))  # deliberately no --force
    store.execute("UPDATE workspaces SET state='CLEANED' WHERE id=?", (row["id"],))
    # Keep the branch as a small recovery pointer. No pruning or chat deletion.
    return {"workspace": row["id"], "state": "CLEANED", "branch_retained": row["branch"]}


def users_of(path):
    """A completion event does not imply background shells have exited."""
    path = path.resolve()
    if Path("/proc").is_dir():
        busy = []
        for process in Path("/proc").iterdir():
            if not process.name.isdigit():
                continue
            try:
                if process.stat().st_uid != os.getuid():
                    continue
                links = [process / "cwd"] + list((process / "fd").iterdir())
                if any(link.resolve().is_relative_to(path) for link in links):
                    busy.append(process.name)
            except FileNotFoundError:
                continue
            except PermissionError:
                # Unrelated nondumpable user services are not owned task jobs. Native
                # background-terminal checks are authoritative for registered jobs;
                # this scan additionally catches visible detached descendants.
                continue
        return busy
    lsof = shutil.which("lsof") or ("/usr/sbin/lsof" if Path("/usr/sbin/lsof").exists() else None)
    if not lsof:
        raise ValueError("Open-file verification unavailable; workspace retained")
    result = subprocess.run([lsof, "-t", "+D", str(path)], text=True, capture_output=True, timeout=20)
    if result.returncode not in {0, 1} or result.stderr.strip():
        raise ValueError("Open-file verification failed; workspace retained")
    return result.stdout.splitlines()

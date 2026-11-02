"""Canonical scope boundaries and Git worktree write coordination."""
import subprocess
import time
from functools import lru_cache
from pathlib import Path


def overlaps(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    return left.is_relative_to(right) or right.is_relative_to(left)


def worktree_root(path):
    return _cached_worktree_root(str(Path(path).resolve()), int(time.monotonic() / 2))


@lru_cache(maxsize=2048)
def _cached_worktree_root(path, epoch):
    # Short TTL includes failed lookups, so repository creation/moves become visible.
    directory = Path(path).resolve()
    while not directory.is_dir() and directory != directory.parent:
        directory = directory.parent
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=directory,
                                text=True, capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(result.stdout.rstrip("\n")).resolve() if result.returncode == 0 else None


def write_overlap(left, right):
    if overlaps(left, right):
        return True
    root = worktree_root(left)
    return root is not None and root == worktree_root(right)

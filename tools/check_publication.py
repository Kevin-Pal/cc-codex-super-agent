#!/usr/bin/env python3
"""Offline file/history checks; findings need review and this is not a security guarantee."""
import argparse
import json
from pathlib import Path
import re
import subprocess

PRIVATE_PARTS = {'private', '_private', 'secrets', '.claude', '.codex', '.agents', 'runs', 'logs', 'state', '.state'}
PRIVATE_NAMES = {'auth.json', 'credentials.json', '.env', '.env.local'}
RULES = {
    'credential-like text': re.compile(rb'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}|AKIA[0-9A-Z]{16}'),
    'concrete home path': re.compile(rb'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'non-public IPv4': re.compile(rb'(?<![0-9])(?:10\.(?:[0-9]{1,3}\.){2}[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})(?![0-9])'),
}


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)


def path_problem(name):
    p = Path(name)
    return bool(set(p.parts) & PRIVATE_PARTS or p.name in PRIVATE_NAMES or p.suffix in {'.pem', '.key', '.db', '.sqlite', '.sqlite3', '.jsonl', '.log'} or '.local.' in p.name)


def scan_bytes(raw):
    return [label for label, pattern in RULES.items() if pattern.search(raw)]


def history_findings(root):
    errors, blobs = [], {}
    commits = git(root, 'rev-list', '--all').decode().splitlines()
    for commit in commits:
        fields = git(root, 'show', '-s', '--format=%ae%x00%ce%x00%B', commit).decode().split('\0', 2)
        for address in fields[:2]:
            if not address.endswith('@users.noreply.github.com'):
                errors.append('Review commit identity: ' + commit[:12])
        errors += ['History message ' + label + ': ' + commit[:12] for label in scan_bytes(fields[2].encode())]
        for row in git(root, 'ls-tree', '-rz', commit).split(b'\0'):
            if not row:
                continue
            meta, name = row.split(b'\t', 1)
            mode, kind, oid = meta.split()
            if kind != b'blob':
                continue
            name = name.decode()
            if path_problem(name):
                errors.append('Private historical path: ' + name + ' at ' + commit[:12])
            if mode == b'120000':
                errors.append('Review historical symlink: ' + name)
            blobs.setdefault(oid.decode(), set()).add(name)
    for oid, names in blobs.items():
        raw = git(root, 'cat-file', 'blob', oid)
        errors += ['History ' + label + ': ' + sorted(names)[0] for label in scan_bytes(raw)]
    return errors, len(commits), len(blobs)


def check(root, history=False):
    root = root.resolve()
    errors = []
    state = json.loads((root / '.release/preparation.json').read_text())
    expected = {'project': 'cc-codex-super-agent', 'phase': 'publication-ready', 'license': 'MIT',
                'runtime_exported': True, 'skills_exported': True, 'visibility_change': 'owner-only',
                'automatic_snapshot_sync': False, 'publication_workflow_enabled': False}
    for key, value in expected.items():
        if state.get(key) != value:
            errors.append('Publication boundary drift: ' + key)
    if not (root / 'LICENSE').is_file() or 'MIT License' not in (root / 'LICENSE').read_text():
        errors.append('Missing MIT license')
    files = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0')
    paths = sorted(set(p.decode() for p in files if p))
    for name in paths:
        p = root / name
        if path_problem(name):
            errors.append('Private instance path: ' + name)
        if p.is_symlink() or not p.resolve().is_relative_to(root):
            errors.append('Review symlink/out-of-tree file: ' + name)
            continue
        if not p.is_file():
            errors.append('Missing file: ' + name)
            continue
        raw = p.read_bytes()
        if len(raw) > 1024 * 1024:
            errors.append('Oversize file: ' + name)
            continue
        errors += [label + ': ' + name for label in scan_bytes(raw)]
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            errors.append('Review binary: ' + name)
            continue
        if p.suffix == '.md':
            for link in re.findall(r'\]\(([^)]+)\)', text):
                target = link.split('#', 1)[0].strip('<>')
                if not target or '://' in target or target.startswith('mailto:'):
                    continue
                resolved = (p.parent / target).resolve()
                if not resolved.is_relative_to(root) or not resolved.exists():
                    errors.append('Broken/out-of-tree link: ' + name)
        if p.name == 'CLAUDE.md' and (text.strip() != '@AGENTS.md' or not (p.parent / 'AGENTS.md').is_file()):
            errors.append('Shared entry drift: ' + name)
    # No CI that could unexpectedly publish artifacts/credentials in this snapshot.
    if list((root / '.github/workflows').glob('*')):
        errors.append('Workflow requires explicit review')
    from sync_skill_references import sync
    errors += ['Stale generated reference: ' + name for name in sync(root, check=True)]
    commits = blobs = 0
    if history:
        past, commits, blobs = history_findings(root)
        errors.extend(past)
    return {'ok': not errors, 'files_checked': len(paths), 'history_commits_checked': commits,
            'history_blobs_checked': blobs, 'errors': sorted(set(errors)), 'github_visibility_checked': False,
            'complete_secret_detection_guaranteed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', action='store_true')
    args = parser.parse_args()
    report = check(Path(__file__).resolve().parents[1], args.history)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['ok'] else 1)

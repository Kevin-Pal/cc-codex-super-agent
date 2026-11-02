#!/usr/bin/env python3
"""Materialize maintained skill references from canonical in-repository guides."""
import argparse
import json
import os
from pathlib import Path
import re


def expected(root, target, source):
    root = root.resolve()
    guide = (root / source).resolve()
    destination = (root / target).resolve()
    if not guide.is_relative_to(root) or not destination.is_relative_to(root):
        raise ValueError('Reference mapping escapes repository')
    def link(match):
        raw = match[1]
        if '://' in raw or raw.startswith(('#', 'mailto:')):
            return match[0]
        path, separator, anchor = raw.partition('#')
        resolved = (guide.parent / path.strip('<>')).resolve()
        if not resolved.is_relative_to(root) or not resolved.exists():
            raise ValueError('Invalid canonical guide link: ' + source)
        return '](' + os.path.relpath(resolved, destination.parent) + (separator + anchor if separator else '') + ')'
    return re.sub(r'\]\(([^)]+)\)', link, guide.read_text())


def sync(root, check=False):
    mapping = json.loads((root / '.release/skill-reference-map.json').read_text())
    drift = []
    for target, source in mapping.items():
        content = expected(root, target, source)
        path = root / target
        if not path.exists() or path.read_text() != content:
            drift.append(target)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    return drift


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    drift = sync(Path(__file__).resolve().parents[1], args.check)
    print(json.dumps({'ok': not drift or not args.check, 'references_changed': drift}))
    raise SystemExit(1 if args.check and drift else 0)

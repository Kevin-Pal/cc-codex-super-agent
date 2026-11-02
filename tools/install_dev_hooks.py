#!/usr/bin/env python3
"""Opt in to this repository's pre-push check without replacing other hooks."""
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
configured = subprocess.run(['git', '-C', str(root), 'config', '--get', 'core.hooksPath'], capture_output=True, text=True)
if configured.returncode == 0 and configured.stdout.strip() != '.githooks':
    raise SystemExit('Another hooksPath is configured; integrate this check with its owner.')
existing = root / '.git/hooks/pre-push'
if existing.exists():
    raise SystemExit('An existing pre-push hook needs manual integration; nothing changed.')
subprocess.run(['git', '-C', str(root), 'config', '--local', 'core.hooksPath', '.githooks'], check=True)
print('Repository-local publication check enabled; no global configuration changed.')

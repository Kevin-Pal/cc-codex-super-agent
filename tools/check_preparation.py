#!/usr/bin/env python3
"""Compatibility entrypoint for the publication checker."""
import json
from pathlib import Path
from check_publication import check
if __name__ == '__main__':
    report = check(Path(__file__).resolve().parents[1])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['ok'] else 1)

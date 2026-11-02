import contextlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from claude_codex_workflow.store import Store


class StorePermissionTests(unittest.TestCase):
    def test_new_database_and_recreated_sidecars_are_private_under_permissive_umask(self):
        # Isolate the process-wide umask from pytest and any other test threads.
        script = """
import json, os, stat, sys
from pathlib import Path
from claude_codex_workflow.store import Store

root = Path(sys.argv[1])
os.umask(int(sys.argv[2], 8))
modes = []
for _ in range(2):
    with Store(root) as store:
        modes.append([stat.S_IMODE((root / name).stat().st_mode) for name in
                      ('state.sqlite3', 'state.sqlite3-wal', 'state.sqlite3-shm')])
probe = root / 'umask-probe'
probe.write_text('unrelated file')
print(json.dumps({'database': modes, 'directory': stat.S_IMODE(root.stat().st_mode),
                  'probe': stat.S_IMODE(probe.stat().st_mode)}))
"""
        source = str(Path(__file__).resolve().parents[1] / "src")
        for mask, probe_mode in [("000", 0o666), ("022", 0o644)]:
            with self.subTest(umask=mask), tempfile.TemporaryDirectory() as temp:
                result = subprocess.run([sys.executable, "-c", script, temp, mask],
                                        env={**os.environ, "PYTHONPATH": source},
                                        text=True, capture_output=True, check=True, timeout=15)
                self.assertEqual(json.loads(result.stdout), {
                    "database": [[0o600, 0o600, 0o600], [0o600, 0o600, 0o600]],
                    "directory": 0o700, "probe": probe_mode,
                })

    def test_open_hardens_existing_sidecars_without_losing_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = [root / ("state.sqlite3" + suffix) for suffix in ("", "-wal", "-shm")]
            with contextlib.closing(sqlite3.connect(paths[0])) as legacy:
                legacy.execute("PRAGMA journal_mode=WAL")
                legacy.execute("CREATE TABLE preserved (value TEXT)")
                legacy.execute("INSERT INTO preserved VALUES ('keep existing state')")
                legacy.commit()
                for path in paths:
                    path.chmod(0o644)
                paths[0].chmod(0o600)
                with Store(root) as store:
                    self.assertEqual([stat.S_IMODE(path.stat().st_mode) for path in paths], [0o600] * 3)
                    self.assertEqual(store.one("SELECT value FROM preserved")["value"], "keep existing state")
                    store.execute("INSERT INTO preserved VALUES ('new state')")
                    self.assertEqual(legacy.execute("SELECT COUNT(*) FROM preserved").fetchone()[0], 2)

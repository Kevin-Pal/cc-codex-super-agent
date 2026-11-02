"""Private transactional registry. Native conversation history stays in Codex."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

TERMINAL = {"READY", "BLOCKED", "FAILED", "CANCELLED", "INCONCLUSIVE", "ACCEPTED", "REJECTED"}


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.lock = threading.RLock()
        database = self.root / "state.sqlite3"
        self.db = sqlite3.connect(database, check_same_thread=False)
        # SQLite's Unix VFS gives new WAL/SHM files the main database's mode.
        # Set it before enabling WAL, without changing the process-wide umask.
        database.chmod(0o600)
        for suffix in ("-wal", "-shm"):
            try:
                Path(str(database) + suffix).chmod(0o600)
            except FileNotFoundError:
                pass  # Sidecars may be absent or removed by the last connection.
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=10000")
        # Fail on corruption; never recreate a database that failed to open.
        if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Registry integrity failure; preserve it for recovery")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        INSERT OR IGNORE INTO meta VALUES ('schema','1');
        CREATE TABLE IF NOT EXISTS routers (
          id TEXT PRIMARY KEY,name TEXT NOT NULL,cwd TEXT NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS workers (
          id TEXT PRIMARY KEY,kind TEXT NOT NULL,origin TEXT NOT NULL,router TEXT NOT NULL,
          name TEXT NOT NULL,stream TEXT,cwd TEXT NOT NULL,tier TEXT NOT NULL,
          permission TEXT NOT NULL,mode TEXT NOT NULL DEFAULT 'automatic',
          active_turn TEXT,created REAL NOT NULL,updated REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS stream_owner ON workers(router,cwd,stream)
          WHERE stream IS NOT NULL AND kind='worker' AND mode!='released';
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY,worker TEXT NOT NULL,router TEXT NOT NULL,key TEXT NOT NULL,
          state TEXT NOT NULL,prompt TEXT NOT NULL,authorization TEXT NOT NULL,
          model TEXT,effort TEXT,turn TEXT,result TEXT,error TEXT,baseline TEXT,
          created REAL NOT NULL,updated REAL NOT NULL,deadline REAL NOT NULL,
          notified REAL,UNIQUE(router,key));
        CREATE UNIQUE INDEX IF NOT EXISTS native_turn ON tasks(worker,turn) WHERE turn IS NOT NULL;
        CREATE TABLE IF NOT EXISTS events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT,worker TEXT,task TEXT,kind TEXT NOT NULL,
          payload TEXT NOT NULL,created REAL NOT NULL,event_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS leases (
          router TEXT NOT NULL,path TEXT NOT NULL,expires REAL NOT NULL,reason TEXT NOT NULL,
          PRIMARY KEY(router,path));
        """)
        version = self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]
        if version not in {"1", "2"}:
            raise RuntimeError("Unsupported registry schema; no automatic destructive migration")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("""CREATE TABLE IF NOT EXISTS takeovers (
                id TEXT PRIMARY KEY,router TEXT NOT NULL,scope TEXT NOT NULL,reason TEXT NOT NULL,
                created REAL NOT NULL,expires REAL NOT NULL,released REAL,note TEXT)""")
            # Additive extensions stay readable by 0.2.0; normalize the earlier schema-2 label.
            self.db.execute("UPDATE meta SET value='1' WHERE key='schema'")
            worker_columns = {row[1] for row in self.db.execute("PRAGMA table_info(workers)")}
            if "pinned" not in worker_columns:
                self.db.execute("ALTER TABLE workers ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(tasks)")}
            for column in ("run_seconds", "queue_deadline", "started"):
                if column not in columns:
                    self.db.execute("ALTER TABLE tasks ADD COLUMN " + column + " REAL")
            self.db.execute("UPDATE tasks SET run_seconds=MAX(60,deadline-created) WHERE run_seconds IS NULL")
            self.db.execute("UPDATE tasks SET queue_deadline=deadline WHERE queue_deadline IS NULL")
            self.db.execute("UPDATE tasks SET started=updated,deadline=updated+run_seconds WHERE state='RUNNING' AND started IS NULL")

    def close(self):
        with self.lock:
            self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def rows(self, query, args=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(query, args)]

    def one(self, query, args=()):
        rows = self.rows(query, args)
        return rows[0] if rows else None

    def execute(self, query, args=()):
        with self.lock, self.db:
            return self.db.execute(query, args).rowcount

    def worker(self, worker_id):
        row = self.one("SELECT * FROM workers WHERE id=?", (worker_id,))
        if not row:
            raise ValueError("Unknown Worker: use its exact registered thread ID")
        return row

    def task(self, task_id):
        row = self.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not row:
            raise ValueError("Unknown task ID")
        return row

    def roster(self, router, query=None, limit=None, include_released=False):
        """Find only this Router's registered persistent sessions, without loading history."""
        if query is not None and (not isinstance(query, str) or not query.strip()):
            raise ValueError("Roster query must be nonempty text")
        if limit is not None and (type(limit) is not int or not 1 <= limit <= 1000):
            raise ValueError("Roster limit must be 1..1000")
        if type(include_released) is not bool:
            raise ValueError("include_released must be boolean")
        where = "w.router=? AND w.kind!='temp'"
        params = [router]
        if not include_released:
            where += " AND w.mode!='released'"
        if query is not None:
            where += " AND (instr(lower(w.name),lower(?)) OR instr(lower(coalesce(w.stream,'')),lower(?)) OR instr(w.id,?) OR instr(lower(w.cwd),lower(?)))"
            params.extend([query.strip()] * 4)
        rows = self.rows("""SELECT w.*,
            (w.active_turn IS NOT NULL OR EXISTS(SELECT 1 FROM tasks t WHERE t.worker=w.id AND t.state IN ('QUEUED','DISPATCHING','RUNNING'))) AS busy,
            EXISTS(SELECT 1 FROM tasks t WHERE t.worker=w.id AND t.state IN ('READY','BLOCKED','FAILED','INCONCLUSIVE')) AS pending_review,
            max(w.updated,coalesce((SELECT max(t.updated) FROM tasks t WHERE t.worker=w.id),w.created)) AS last_activity
            FROM workers w WHERE """ + where + """
            ORDER BY (w.mode='released'),busy DESC,pending_review DESC,w.pinned DESC,last_activity DESC,w.id""", params)
        for row in rows:
            row["activity"] = "busy" if row.pop("busy") else "needs_review" if row["pending_review"] else "idle"
            row["pinned"] = bool(row["pinned"])
            row["pending_review"] = bool(row["pending_review"])
        return rows if limit is None else rows[:limit]

    def event(self, kind, worker=None, task=None, payload=None, key=None):
        self.execute("INSERT OR IGNORE INTO events(worker,task,kind,payload,created,event_key) VALUES(?,?,?,?,?,?)",
                     (worker, task, kind, json.dumps(payload or {}, ensure_ascii=False), time.time(), key))

    def _takeover_event(self, kind, takeover):
        # Caller owns the transaction so the lease and its audit event commit together.
        self.db.execute("INSERT INTO events(kind,payload,created) VALUES(?,?,?)",
                        (kind, json.dumps({**takeover, "label": "Router direct work"}, ensure_ascii=False), time.time()))

    def start_takeover(self, router, scope, reason, hours):
        now = time.time()
        takeover = {"id": str(uuid.uuid4()), "router": router, "scope": scope, "reason": reason,
                    "created": now, "expires": now + hours * 3600, "released": None, "note": None}
        with self.lock, self.db:
            self.db.execute("INSERT INTO takeovers VALUES(?,?,?,?,?,?,NULL,NULL)",
                            (takeover["id"], router, json.dumps(scope), reason, now, takeover["expires"]))
            self._takeover_event("takeover_started", takeover)
        return takeover

    def _end_takeover(self, row, note, ended):
        takeover = {**dict(row), "scope": json.loads(row["scope"]), "released": ended, "note": note}
        changed = self.db.execute("UPDATE takeovers SET released=?,note=? WHERE id=? AND released IS NULL",
                                  (ended, note, row["id"])).rowcount
        if changed:
            self._takeover_event("takeover_released", takeover)
        return takeover

    def active_takeovers(self, router=None):
        now = time.time()
        with self.lock, self.db:
            # Expiry never requires a running scheduler; the next read records its end once.
            for row in self.db.execute("SELECT * FROM takeovers WHERE released IS NULL AND expires<=?", (now,)).fetchall():
                self._end_takeover(row, "expired", row["expires"])
            query = "SELECT * FROM takeovers WHERE released IS NULL AND expires>?"
            args = (now,)
            if router is not None:
                query += " AND router=?"
                args += (router,)
            return [{**dict(row), "scope": json.loads(row["scope"]), "remaining_seconds": max(0, row["expires"] - now)}
                    for row in self.db.execute(query + " ORDER BY created,id", args)]

    def release_takeovers(self, router, note=None):
        self.active_takeovers()  # Record already-expired leases as expired, not explicitly released.
        with self.lock, self.db:
            rows = self.db.execute("SELECT * FROM takeovers WHERE router=? AND released IS NULL", (router,)).fetchall()
            return [self._end_takeover(row, note, time.time()) for row in rows]

    def register(self, thread_id, kind, router, name, cwd, tier="hard", permission="trusted-worker", stream=None, origin=None):
        if kind not in {"worker", "personal", "temp"}:
            raise ValueError("Invalid session kind")
        now = time.time()
        self.execute("INSERT INTO workers(id,kind,origin,router,name,stream,cwd,tier,permission,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (thread_id, kind, origin or kind, router, name, stream, cwd, tier, permission, now, now))
        self.event("registered", worker=thread_id, payload={"kind": kind, "router": router})
        return self.worker(thread_id)

    def enqueue(self, worker, router, key, prompt, authorization, model, effort, minutes=45, baseline=None, queue_minutes=45):
        if not prompt.strip() or not authorization.strip():
            raise ValueError("A goal and authorization reference are required")
        if not 1 <= minutes <= 1440:
            raise ValueError("Deadline must be 1..1440 minutes")
        if not 1 <= queue_minutes <= 1440:
            raise ValueError("Queue deadline must be 1..1440 minutes")
        with self.lock, self.db:
            prior = self.one("SELECT * FROM tasks WHERE router=? AND key=?", (router, key))
            if prior:
                if (prior["worker"], prior["prompt"], prior["authorization"]) != (worker, prompt, authorization):
                    raise ValueError("Idempotency key reused for different work")
                return prior
            task_id = str(uuid.uuid4())
            now = time.time()
            # Keep deadline readable by old code; reset it from run_seconds on RUNNING.
            self.db.execute("INSERT INTO tasks(id,worker,router,key,state,prompt,authorization,model,effort,created,updated,deadline,baseline,run_seconds,queue_deadline) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (task_id, worker, router, key, "QUEUED", prompt, authorization, model, effort, now, now, now + minutes * 60, baseline, minutes * 60, now + queue_minutes * 60))
            self.event("queued", worker=worker, task=task_id)
        return self.task(task_id)

    def finish(self, task_id, state, result=None, error=None):
        if state not in TERMINAL:
            raise ValueError("Invalid terminal state")
        with self.lock, self.db:
            task = self.task(task_id)
            if task["state"] in TERMINAL:
                return task
            self.db.execute("UPDATE tasks SET state=?,result=?,error=?,updated=? WHERE id=?",
                            (state, result, error, time.time(), task_id))
            self.event("result", worker=task["worker"], task=task_id, payload={"state": state}, key="result:" + task_id)
        return self.task(task_id)

    def decide(self, task_id, router, accepted, note):
        task = self.task(task_id)
        if task["router"] != router:
            raise ValueError("Only the assigned Router may record acceptance")
        if task["state"] not in {"READY", "REJECTED", "ACCEPTED"}:
            raise ValueError("Only a completed READY task can be accepted/rejected")
        state = "ACCEPTED" if accepted else "REJECTED"
        self.execute("UPDATE tasks SET state=?,updated=? WHERE id=?", (state, time.time(), task_id))
        self.event("review", worker=task["worker"], task=task_id, payload={"state": state, "note": note})
        return self.task(task_id)

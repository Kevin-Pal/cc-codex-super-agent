import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from claude_codex_workflow.manager import Manager
from claude_codex_workflow.hooks import context
from claude_codex_workflow.workspaces import git
from claude_codex_workflow.service import dispatch
from claude_codex_workflow.rpc import RpcError
from test_workflow import FakeNative


class ReloadNative(FakeNative):
    def __init__(self):
        super().__init__()
        self.unloaded = set()
        self.archive_calls = []
        self.children = []
        self.background = []
        self.resume_params = []
        self.unarchive_calls = []

    def request(self, method, params):
        tid = params.get('threadId')
        if method == 'thread/list':
            return {'data': self.children}
        if method == 'thread/backgroundTerminals/list':
            return {'data': self.background}
        if method == 'thread/archive':
            self.unloaded.add(tid); self.archive_calls.append(tid)
            return {}
        if method == 'thread/unarchive':
            self.unarchive_calls.append(tid)
            return {'thread': self.threads[tid]}
        if method == 'thread/resume' and tid in self.unloaded:
            self.threads[tid]['cwd'] = params.get('cwd', self.threads[tid]['cwd'])
            self.unloaded.remove(tid)
        if method == 'thread/resume':
            self.resume_params.append(dict(params))
        return super().request(method, params)


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.p = self.root / 'project'; self.p.mkdir()
        (self.p / 'AGENTS.md').write_text('Shared project decision one.\n')
        self.native = ReloadNative()
        self.m = Manager(self.root / 'state', client=self.native)
        self.m.register_router('r', 'Router', str(self.p))

    def tearDown(self):
        self.m.close(); self.temp.cleanup()

    def open(self, **kwargs):
        with patch('shutil.which', return_value=None):
            return self.m.open('r', 'Router', str(self.p), 'Direction', stream=kwargs.pop('stream', 'main'), **kwargs)

    def repo(self, path=None):
        path = path or self.p
        subprocess.run(['git', 'init', '-q', str(path)], check=True)
        git(path, 'add', '.')
        git(path, '-c', 'user.name=Synthetic', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'synthetic base')
        return path

    def send(self, opened):
        with patch('shutil.which', return_value=None):
            return self.m.send(opened['worker']['id'], 'r', 'Read assigned inputs; return observed output',
                               'synthetic owner instruction', opened['sync']['sync_token'])

    def complete(self, worker_id):
        self.native.complete(worker_id)
        turn = self.native.threads[worker_id]['turns'][-1]
        self.m.on_event({'method': 'turn/completed', 'params': {'threadId': worker_id, 'turn': turn}})
        self.m.reconcile(self.m.store.worker(worker_id))

    def test_subdirectory_creation_rejected_without_rebinding_or_native_thread(self):
        a = self.open(); sub = self.p / 'child'; sub.mkdir()
        with self.assertRaisesRegex(ValueError, 'Router project'):
            self.m.open('r', 'Router', str(sub), 'Other', stream='other')
        self.assertEqual(len(self.native.threads), 1)
        self.assertEqual(self.m.store.one("SELECT cwd FROM routers WHERE id='r'")['cwd'], str(self.p))
        self.assertEqual(self.open()['worker']['id'], a['worker']['id'])

    def test_formal_isolation_rejected_and_user_started_child_router_is_independent(self):
        with self.assertRaisesRegex(ValueError, 'temporary'):
            self.open(isolation='worktree')
        sub = self.p / 'child'; sub.mkdir()
        with patch('shutil.which', return_value=None):
            self.m.register_router('child-router', 'Child', str(sub))
            child = self.m.open('child-router', 'Child', str(sub), 'Child work', stream='c')
        self.assertEqual(child['worker']['cwd'], str(sub))

    def test_symlink_alias_same_project_is_accepted(self):
        self.open(); alias = self.root / 'alias'; alias.symlink_to(self.p, target_is_directory=True)
        with patch('shutil.which', return_value=None):
            reused = self.m.open('r', 'Router', str(alias), 'Direction', stream='main')
        self.assertEqual(reused['worker']['cwd'], str(self.p))

    def test_hook_keeps_launch_root_after_cd_and_exports_it(self):
        sub = self.p / 'child'; sub.mkdir()
        log = self.root / 'session.jsonl'
        log.write_text(json.dumps({'cwd': str(self.p)}) + '\n')
        env = self.root / 'session.env'
        with patch.dict(os.environ, {'CLAUDE_ENV_FILE': str(env)}, clear=True), \
                patch('claude_codex_workflow.hooks.call', side_effect=lambda op, args: dispatch(self.m, {'operation': op, 'params': args})), \
                contextlib.redirect_stdout(io.StringIO()):
            context({'session_id': 'r', 'cwd': str(sub), 'transcript_path': str(log)}, start=True)
        self.assertIn('CCW_PROJECT_ROOT=' + str(self.p), env.read_text())

    def test_external_inspect_and_adopt_never_rebind_requesting_project(self):
        self.open(); other = self.root / 'other'; other.mkdir()
        tid = self.native.request('thread/start', {'cwd': str(other), 'ephemeral': False})['thread']['id']
        before = dict(self.native.threads[tid])
        info = self.m.inspect(tid, 'r')
        self.assertFalse(info['control_changed']); self.assertEqual(before, self.native.threads[tid])
        self.assertIsNone(self.m.store.one('SELECT id FROM workers WHERE id=?', (tid,)))
        self.m.adopt(tid, 'r', 'Router')
        self.assertEqual(self.m.store.one("SELECT cwd FROM routers WHERE id='r'")['cwd'], str(self.p))
        self.assertEqual(self.m.project(self.m.store.worker(tid))['project_root'], str(other))

    def test_native_cwd_drift_blocks_send_and_already_queued_task(self):
        a = self.open(); task = self.send(a)
        self.native.threads[a['worker']['id']]['cwd'] = str(self.root)
        with self.assertRaisesRegex(ValueError, 'cwd changed'):
            self.send(a)
        self.assertFalse(self.m._dispatch(self.m.store.task(task['task_id'])))
        self.assertEqual(self.m.store.task(task['task_id'])['state'], 'BLOCKED')
        self.assertFalse(self.native.started)

    def test_repair_requires_idle_reload_and_preserves_id_and_manual_state(self):
        a = self.open(); tid = a['worker']['id']; old = self.p / 'old'; old.mkdir()
        self.native.threads[tid]['cwd'] = str(old)
        self.m.store.execute('UPDATE workers SET cwd=? WHERE id=?', (str(old), tid))
        with self.assertRaisesRegex(ValueError, 'reload'):
            self.m.repair(tid, 'r', 'owner requests path correction')
        repaired = self.m.repair(tid, 'r', 'owner requests path correction', reload=True)
        self.assertEqual(repaired['worker']['id'], tid)
        self.assertEqual(repaired['worker']['cwd'], str(self.p))
        self.assertEqual(self.native.archive_calls, [tid])
        self.m.store.execute("UPDATE workers SET mode='manual' WHERE id=?", (tid,))
        with self.assertRaisesRegex(ValueError, 'human control'):
            self.m.repair(tid, 'r', 'path repair', reload=True)

    def test_isolated_temp_uses_central_rules_and_stale_queue_is_blocked(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree')
        self.assertNotEqual(a['worker']['cwd'], str(self.p))
        self.assertEqual(a['sync']['project_root'], str(self.p))
        task = self.send(a)
        (self.p / 'AGENTS.md').write_text('New central instruction not yet committed.\n')
        self.m._dispatch(self.m.store.task(task['task_id']))
        self.assertEqual(self.m.store.task(task['task_id'])['state'], 'BLOCKED')

    def test_nested_temp_and_formal_can_dispatch_but_two_formal_writers_queue(self):
        self.repo(); a = self.open(); b = self.open(kind='temp', isolation='worktree'); d = self.open(stream='second')
        ta, tb, td = self.send(a), self.send(b), self.send(d)
        self.assertTrue(self.m._dispatch(self.m.store.task(ta['task_id'])))
        self.assertTrue(self.m._dispatch(self.m.store.task(tb['task_id'])))
        self.assertFalse(self.m._dispatch(self.m.store.task(td['task_id'])))

    def test_cleanup_requires_acceptance_and_preserves_untracked_ignored_and_commits(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); resource = a['sync']['workspace']
        task = self.send(a); self.m._dispatch(self.m.store.task(task['task_id']))
        self.complete(a['worker']['id'])
        with self.assertRaisesRegex(ValueError, 'Accept'):
            self.m.workspace('r', resource, cleanup=True)
        tree = Path(a['worker']['cwd']); (tree / 'result.txt').write_text('keep this artifact')
        result = self.m.review(task['task_id'], 'r', True, 'verified result')
        self.assertIn('workspace_retained', result); self.assertTrue(tree.exists())
        (tree / 'result.txt').unlink()
        with patch('claude_codex_workflow.workspaces.users_of', return_value=['background-job']):
            with self.assertRaisesRegex(ValueError, 'processes'):
                self.m.workspace('r', resource, cleanup=True)
        (tree / '.gitignore').write_text('ignored-output\n'); git(tree, 'add', '.gitignore')
        git(tree, '-c', 'user.name=Synthetic', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'new change')
        (tree / 'ignored-output').write_text('keep ignored artifact')
        with self.assertRaisesRegex(ValueError, 'ignored'):
            self.m.workspace('r', resource, cleanup=True)
        (tree / 'ignored-output').unlink()
        with self.assertRaisesRegex(ValueError, 'not integrated'):
            self.m.workspace('r', resource, cleanup=True)
        git(self.p, 'merge', '--ff-only', git(tree, 'rev-parse', 'HEAD'))
        self.assertEqual(self.m.workspace('r', resource, cleanup=True)['state'], 'CLEANED')
        self.assertTrue(self.m.store.task(task['task_id'])['result'])

    def test_empty_accepted_workspace_auto_cleanup_and_symlink_namespace_refusal(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); task = self.send(a)
        self.m._dispatch(self.m.store.task(task['task_id'])); self.complete(a['worker']['id'])
        result = self.m.review(task['task_id'], 'r', True, 'verified')
        self.assertEqual(result['workspace_cleanup']['state'], 'CLEANED')
        ns = self.p / '.claude/cc-codex-super-agent'
        import shutil
        shutil.rmtree(ns); ns.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.open(kind='temp', isolation='worktree')

    def test_dirty_source_requires_explicit_base_and_no_implicit_copy(self):
        self.repo(); (self.p / 'uncommitted.txt').write_text('not a snapshot')
        with self.assertRaisesRegex(ValueError, 'explicit committed'):
            self.open(kind='temp', isolation='worktree')
        a = self.open(kind='temp', isolation='worktree', base='HEAD')
        self.assertFalse((Path(a['worker']['cwd']) / 'uncommitted.txt').exists())

    def test_reload_refuses_to_archive_descendants(self):
        a = self.open(); tid = a['worker']['id']
        self.native.threads[tid]['cwd'] = str(self.root)
        self.native.children = [{'id': 'existing-child'}]
        with self.assertRaisesRegex(ValueError, 'descendant'):
            self.m.repair(tid, 'r', 'owner requested repair', reload=True)
        self.assertFalse(self.native.archive_calls)

    def test_native_background_terminal_blocks_cleanup(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); task = self.send(a)
        self.m._dispatch(self.m.store.task(task['task_id'])); self.complete(a['worker']['id'])
        self.native.background = [{'processId': 'native-job'}]
        result = self.m.review(task['task_id'], 'r', True, 'verified result')
        self.assertIn('background', result['workspace_retained'])
        self.assertTrue(Path(a['worker']['cwd']).exists())

    def test_visible_detached_process_blocks_cleanup(self):
        import sys
        self.repo(); a = self.open(kind='temp', isolation='worktree'); task = self.send(a)
        self.m._dispatch(self.m.store.task(task['task_id'])); self.complete(a['worker']['id'])
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], cwd=a['worker']['cwd'])
        try:
            result = self.m.review(task['task_id'], 'r', True, 'verified result')
            self.assertIn('processes', result['workspace_retained'])
        finally:
            child.terminate(); child.wait(timeout=10)
        self.assertEqual(self.m.workspace('r', a['sync']['workspace'], cleanup=True)['state'], 'CLEANED')

    def test_nested_repository_isolation_remains_owned_by_parent_project(self):
        self.repo(); nested = self.p / 'paper'; nested.mkdir(); (nested / 'text.txt').write_text('base')
        self.repo(nested)
        a = self.open(kind='temp', isolation='worktree', repo=str(nested))
        self.assertEqual(a['sync']['project_root'], str(self.p))
        self.assertNotEqual(a['worker']['cwd'], str(nested))
        self.assertTrue((Path(a['worker']['cwd']) / 'text.txt').exists())

    def test_unregistered_router_cannot_guess_project_or_adopt_external_path(self):
        with self.assertRaisesRegex(ValueError, 'Register'):
            self.m.open('unknown', 'Unknown', str(self.p), 'work', stream='work')
        with self.assertRaisesRegex(ValueError, 'Register'):
            self.m.adopt('not-owned', 'unknown', 'Unknown')
        self.assertIsNone(self.m.store.one("SELECT * FROM routers WHERE id='unknown'"))

    def test_rebound_stream_is_not_duplicated_before_legacy_repair(self):
        a = self.open(); p = self.root / 'new-entry'; p.mkdir()
        self.m.register_router('r', 'Router', str(p), rebind=True, reason='owner changes entry')
        with self.assertRaisesRegex(ValueError, 'repair'):
            self.m.open('r', 'Router', str(p), 'Direction', stream='main')
        self.assertEqual(len(self.native.threads), 1)
        self.assertTrue(self.m.store.roster('r')[0]['needs_repair'])

    def test_native_start_uncertainty_is_named_and_not_blindly_replayed_or_deleted(self):
        self.repo(); original = self.native.request
        def fail(method, params):
            if method == 'thread/start':
                raise TimeoutError('lost acknowledgment')
            return original(method, params)
        with patch.object(self.native, 'request', side_effect=fail):
            with self.assertRaisesRegex(ValueError, 'workspace retained'):
                self.open(kind='temp', isolation='worktree')
        row = self.m.workspace('r')[0]
        self.assertEqual(row['state'], 'UNCERTAIN'); self.assertTrue(Path(row['path']).exists())
        with self.assertRaisesRegex(ValueError, 'Resolve prepared'):
            self.open(kind='temp', isolation='worktree')
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.m.workspace('r', row['id'], discard=True, reason='inspection')

    def test_worker_project_registration_rolls_back_as_one_transaction(self):
        self.m.store.execute("CREATE TRIGGER fail_project BEFORE INSERT ON worker_projects BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises(Exception):
            self.open()
        self.assertEqual(self.m.store.rows('SELECT * FROM workers'), [])

    def test_invalid_workspace_does_not_starve_another_router(self):
        import shutil
        self.repo(); a = self.open(kind='temp', isolation='worktree'); bad = self.send(a)
        shutil.rmtree(Path(a['worker']['cwd']))
        other = self.root / 'other-project'; other.mkdir(); self.m.register_router('other', 'Other', str(other))
        with patch('shutil.which', return_value=None):
            b = self.m.open('other', 'Other', str(other), 'work', stream='other')
            good = self.m.send(b['worker']['id'], 'other', 'Independent work', 'owner', b['sync']['sync_token'])
        self.m._schedule_once()
        self.assertEqual(self.m.store.task(bad['task_id'])['state'], 'BLOCKED')
        self.assertEqual(self.m.store.task(good['task_id'])['state'], 'RUNNING')

    def test_cancelled_clean_temp_has_explicit_discard_exit_and_forget_is_checked(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); task = self.send(a)
        self.m.cancel(task['task_id'], 'r')
        row = self.m.workspace('r', a['sync']['workspace'])
        with self.assertRaisesRegex(ValueError, 'reason'):
            self.m.workspace('r', row['id'], discard=True)
        self.assertEqual(self.m.workspace('r', row['id'], discard=True, reason='cancelled before execution')['state'], 'CLEANED')
        b = self.open(kind='temp', isolation='worktree'); resource = b['sync']['workspace']
        with self.assertRaisesRegex(ValueError, 'absent'):
            self.m.workspace('r', resource, forget=True, reason='checked')
        git(self.p, 'worktree', 'remove', b['worker']['cwd'])
        self.assertEqual(self.m.workspace('r', resource, forget=True, reason='manual Git removal verified')['state'], 'CLEANED')

    def test_repair_restates_readonly_policy_and_recovers_interrupted_archive(self):
        a = self.open(permission='independent-review'); tid = a['worker']['id']
        self.native.threads[tid]['cwd'] = str(self.root)
        self.m.repair(tid, 'r', 'repair readonly reviewer', reload=True)
        params = self.native.resume_params[-1]
        self.assertEqual(params['sandbox'], 'read-only'); self.assertEqual(params['approvalPolicy'], 'never')
        self.assertFalse(params['config']['memories.use_memories'])
        self.m.store.execute('INSERT INTO meta VALUES(?,?)', ('path-reload:' + tid, '{}'))
        self.native.unloaded.add(tid); self.m.recover()
        self.assertIsNone(self.m.store.one('SELECT value FROM meta WHERE key=?', ('path-reload:' + tid,)))

    def test_transient_native_failure_keeps_queue_and_recovers_next_tick(self):
        a = self.open(); task = self.send(a); original = self.native.request
        def timeout(method, params):
            if method == 'thread/read':
                raise TimeoutError('temporary transport timeout')
            return original(method, params)
        with patch.object(self.native, 'request', side_effect=timeout):
            self.m._schedule_once()
        self.assertEqual(self.m.store.task(task['task_id'])['state'], 'QUEUED')
        self.m._schedule_once()
        self.assertEqual(self.m.store.task(task['task_id'])['state'], 'RUNNING')

    def test_readopt_personal_session_preserves_manual_and_paused_control(self):
        other = self.root / 'personal'; other.mkdir()
        tid = self.native.request('thread/start', {'cwd': str(other), 'ephemeral': False})['thread']['id']
        self.m.adopt(tid, 'r', 'Router')
        for mode in ['manual', 'paused', 'external']:
            self.m.store.execute('UPDATE workers SET mode=? WHERE id=?', (mode, tid))
            self.assertEqual(self.m.adopt(tid, 'r', 'Router')['worker']['mode'], mode)

    def test_cleanup_requires_positive_background_schema_and_not_method_not_found(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); task = self.send(a)
        self.m._dispatch(self.m.store.task(task['task_id'])); self.complete(a['worker']['id'])
        original = self.native.request
        def bad_shape(method, params):
            return {} if method == 'thread/backgroundTerminals/list' else original(method, params)
        with patch.object(self.native, 'request', side_effect=bad_shape):
            result = self.m.review(task['task_id'], 'r', True, 'verified')
        self.assertIn('response shape', result['workspace_retained'])
        def missing_method(method, params):
            if method == 'thread/backgroundTerminals/list':
                raise RpcError('{"code":-32601,"message":"Method not found"}')
            return original(method, params)
        with patch.object(self.native, 'request', side_effect=missing_method):
            self.assertIn('Method not found', self.m.review(task['task_id'], 'r', True, 'verified')['workspace_retained'])

    def test_cancel_snapshot_allows_verified_cleanup_after_ephemeral_unload(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); task = self.send(a)
        self.m._dispatch(self.m.store.task(task['task_id'])); self.m.cancel(task['task_id'], 'r')
        original = self.native.request
        def unloaded(method, params):
            if method == 'thread/read':
                raise RpcError('thread is not loaded')
            return original(method, params)
        with patch.object(self.native, 'request', side_effect=unloaded):
            result = self.m.workspace('r', a['sync']['workspace'], discard=True, reason='cancelled and verified stopped')
        self.assertEqual(result['state'], 'CLEANED')

    def test_archive_ack_timeout_restores_visibility_and_clears_recovery_marker(self):
        a = self.open(); tid = a['worker']['id']; self.native.threads[tid]['cwd'] = str(self.root)
        original = self.native.request
        def timeout(method, params):
            result = original(method, params)
            if method == 'thread/archive':
                raise TimeoutError('archive acknowledgment lost')
            return result
        with patch.object(self.native, 'request', side_effect=timeout):
            with self.assertRaises(TimeoutError):
                self.m.repair(tid, 'r', 'owner requested repair', reload=True)
        self.assertIn(tid, self.native.unarchive_calls)
        self.assertIsNone(self.m.store.one('SELECT value FROM meta WHERE key=?', ('path-reload:' + tid,)))

    def test_forget_after_repo_move_preserves_audit_and_does_not_delete_moved_files(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); resource = a['sync']['workspace']
        moved = self.root / 'moved-project'; self.p.rename(moved)
        result = self.m.workspace('r', resource, forget=True, reason='owner moved the complete project; no queued work')
        self.assertEqual(result['state'], 'CLEANED')
        self.assertTrue(moved.exists())
        self.assertTrue(self.m.store.one("SELECT payload FROM events WHERE kind='workspace_forgotten'"))

    def test_idle_housekeeping_retries_accepted_cleanup_after_process_release(self):
        self.repo(); a = self.open(kind='temp', isolation='worktree'); task = self.send(a)
        self.m._dispatch(self.m.store.task(task['task_id'])); self.complete(a['worker']['id'])
        with patch('claude_codex_workflow.workspaces.users_of', return_value=['native-context-grace']):
            self.m.review(task['task_id'], 'r', True, 'verified')
        self.m._schedule_once()
        self.assertEqual(self.m.workspace('r', a['sync']['workspace'])['state'], 'CLEANED')

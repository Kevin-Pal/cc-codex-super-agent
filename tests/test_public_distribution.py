import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from claude_codex_workflow.install import install, uninstall

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from check_publication import history_findings, scan_bytes


class PublicDistributionTests(unittest.TestCase):
    def test_install_preserves_unowned_legacy_sections_and_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / '.claude/skills/codex-delegate').mkdir(parents=True)
            old = home / '.claude/skills/codex-delegate/SKILL.md'
            old.write_text('another package owns this file\n')
            instruction = home / '.claude/CLAUDE.md'
            original = '## 怎么使唤 Codex\nUnrelated user section.\n\n## 协作入口\nUser instructions.\n'
            instruction.write_text(original)
            install(home, 'router', True)
            self.assertTrue(instruction.read_text().startswith(original))
            self.assertEqual(old.read_text(), 'another package owns this file\n')
            uninstall(home, True)
            self.assertEqual(instruction.read_text(), original)

    def test_managed_sources_keep_user_sections_and_rollback_generated_output(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            for directory in ['.agents/global', '.local/bin', '.codex']:
                (home / directory).mkdir(parents=True)
            shared = home / '.agents/global/shared.md'
            worker = home / '.agents/global/codex.md'
            output = home / '.codex/AGENTS.md'
            shared_text = '## 用户与分工\nPrivate user-owned preference.\n'
            worker_text = '## 用户直接给你的任务\nUser-owned workflow.\n'
            shared.write_text(shared_text)
            worker.write_text(worker_text)
            output.write_text('Original generated output.\n')
            (home / '.local/bin/agents-sync').write_text('owned external generator')
            def generate(*args, **kwargs):
                output.write_text(shared.read_text() + worker.read_text())
                return subprocess.CompletedProcess(args[0], 0)
            with patch('claude_codex_workflow.install.subprocess.run', side_effect=generate):
                install(home, 'both', True)
            self.assertTrue(shared.read_text().startswith(shared_text))
            self.assertTrue(worker.read_text().startswith(worker_text))
            self.assertIn('claude-codex-workflow:begin', output.read_text())
            uninstall(home, True)
            self.assertEqual(shared.read_text(), shared_text)
            self.assertEqual(worker.read_text(), worker_text)
            self.assertEqual(output.read_text(), 'Original generated output.\n')

    def test_installed_materialized_skill_links_resolve(self):
        import re
        with tempfile.TemporaryDirectory() as temp:
            result = install(Path(temp), 'both', True)
            release = Path(result['release'])
            for guide in (release / 'skills').rglob('*.md'):
                for raw in re.findall(r'\]\(([^)]+)\)', guide.read_text()):
                    target = raw.split('#', 1)[0].strip('<>')
                    if target and '://' not in target:
                        self.assertTrue((guide.parent / target).exists(), str(guide.relative_to(release)))

    def test_scanner_flags_synthetic_credential_but_not_placeholder(self):
        fake = ('sk-' + 'proj-' + 'x' * 40).encode()
        self.assertIn('credential-like text', scan_bytes(fake))
        self.assertEqual(scan_bytes(b'YOUR_TOKEN_HERE'), [])

    def test_history_audit_finds_deleted_synthetic_secret(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init', '-q')
            git('config', 'user.name', 'Synthetic Author')
            git('config', 'user.email', '1+synthetic@users.noreply.github.com')
            p = root / 'example.txt'
            p.write_text('gh' + 'p_' + 'x' * 40)
            git('add', 'example.txt');git('commit', '-qm', 'Synthetic fixture')
            p.write_text('placeholder')
            git('commit', '-qam', 'Remove fixture')
            findings, commits, blobs = history_findings(root)
            self.assertEqual(commits, 2)
            self.assertTrue(any('credential-like' in item for item in findings))


if __name__ == '__main__':
    unittest.main()

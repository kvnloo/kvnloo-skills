"""Exercise the installer only inside disposable homes and repositories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        skill = self.repo / 'skills' / 'sample'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('---\nname: sample\ndescription: A sample.\n---\n')
        self.manifest = self.repo / 'stack.toml'
        self.manifest.write_text('''schema_version = 1
[harnesses.claude]
directory = "~/.claude-home/skills"
[harnesses.codex]
directory = "~/.agents/skills"
[harnesses.agents]
directory = "~/.agents/skills"
[harnesses.hermes-clean]
directory = "~/.hermes/profiles/clean/skills"
[harnesses.hermes-chiefstaff]
directory = "~/.hermes/profiles/chiefstaff/skills"
[skills.sample]
source = "skills/sample"
harnesses = ["claude", "codex", "agents", "hermes-clean", "hermes-chiefstaff"]
pack = "default"
''')

    def run_cli(self, *args, ok=True, env=None):
        result = subprocess.run([sys.executable, str(ROOT / 'install.py'),
                                 '--home', str(self.home), '--manifest', str(self.manifest),
                                 *args], capture_output=True, text=True, env=env)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def target(self, directory='.claude-home/skills', name='sample'):
        return self.home / directory / name

    def snapshot(self):
        return sorted((str(p.relative_to(self.home)), p.lstat().st_mtime_ns,
                       os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None)
                      for p in self.home.rglob('*'))

    def test_plan_and_tools_change_nothing(self):
        before = self.snapshot()
        self.assertIn('LINK', self.run_cli('--plan').stdout)
        self.run_cli('--tools')
        self.assertEqual(self.snapshot(), before)

    def test_apply_routes_each_harness_and_is_idempotent(self):
        self.run_cli('--apply')
        for directory in ('.claude-home/skills', '.agents/skills',
                          '.hermes/profiles/clean/skills', '.hermes/profiles/chiefstaff/skills'):
            self.assertEqual(self.target(directory).resolve(), self.repo / 'skills/sample')
        before = self.snapshot()
        self.assertIn('No changes', self.run_cli('--apply').stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertIn('managed', self.run_cli('--status').stdout)

    def test_harness_selection(self):
        self.run_cli('--apply', '--harness', 'codex')
        self.assertTrue(self.target('.agents/skills').is_symlink())
        self.assertFalse(self.target().exists())
        self.run_cli('--uninstall', '--harness', 'agents')
        self.assertFalse(self.target('.agents/skills').exists())

    def test_real_folder_is_backed_up_and_restored_byte_for_byte(self):
        target = self.target()
        (target / 'nested').mkdir(parents=True)
        (target / 'nested/data').write_bytes(bytes(range(256)))
        os.chmod(target / 'nested/data', 0o640)
        (target / 'empty').mkdir()
        (target / 'link').symlink_to('nested/data')
        before = self.snapshot()
        self.assertIn('MOVE', self.run_cli('--plan', '--harness', 'claude').stdout)
        self.assertEqual(before, self.snapshot())
        self.run_cli('--apply', '--harness', 'claude')
        state = json.loads((self.home / '.local/state/kvnloo-skills/links.json').read_text())
        record = next(iter(state['links'].values()))
        self.assertTrue(Path(record['original']).is_dir())
        self.run_cli('--uninstall', '--harness', 'claude')
        self.assertEqual((target / 'nested/data').read_bytes(), bytes(range(256)))
        self.assertEqual((target / 'nested/data').stat().st_mode & 0o777, 0o640)
        self.assertEqual(os.readlink(target / 'link'), 'nested/data')
        self.assertTrue((target / 'empty').is_dir())
        self.assertTrue(list((self.home / '.local/state/kvnloo-skills').glob('backup-*/manifest.json')))
        self.run_cli('--uninstall')

    def test_foreign_dangling_symlink_is_moved_and_restored(self):
        target = self.target()
        target.parent.mkdir(parents=True)
        target.symlink_to(self.base / 'missing')
        original = os.readlink(target)
        self.run_cli('--apply', '--harness', 'claude')
        self.run_cli('--uninstall')
        self.assertTrue(target.is_symlink())
        self.assertEqual(os.readlink(target), original)

    def test_uninstall_refuses_user_changes(self):
        self.run_cli('--apply', '--harness', 'claude')
        target = self.target()
        target.unlink()
        target.mkdir()
        (target / 'user-data').write_text('preserve me')
        before = self.snapshot()
        self.run_cli('--uninstall', ok=False)
        self.assertEqual(before, self.snapshot())

    def test_hermes_keeps_name_category_and_usage(self):
        folder = self.home / '.hermes/profiles/chiefstaff/skills'
        original = folder / 'research/sample'
        original.mkdir(parents=True)
        (original / 'SKILL.md').write_text('original')
        (folder / '.usage.json').write_text('{"sample":{"use_count":22}}')
        self.run_cli('--apply', '--harness', 'hermes-chiefstaff')
        self.assertTrue(original.is_symlink())
        self.assertFalse((folder / 'sample').exists())
        self.assertEqual((folder / '.usage.json').read_text(), '{"sample":{"use_count":22}}')
        self.run_cli('--uninstall')
        self.assertEqual((original / 'SKILL.md').read_text(), 'original')

    def test_local_source_at_target_is_retained_without_cycle(self):
        local = self.target('.agents/skills', 'local-sample')
        local.mkdir(parents=True)
        (local / 'SKILL.md').write_text('local')
        with self.manifest.open('a') as f:
            f.write('''[skills.local-sample]
source = "local:~/.agents/skills/local-sample"
harnesses = ["agents", "claude"]
pack = "default"
''')
        self.run_cli('--apply')
        self.assertFalse(local.is_symlink())
        self.assertEqual(self.target(name='local-sample').resolve(), local)
        self.run_cli('--uninstall')
        self.assertEqual((local / 'SKILL.md').read_text(), 'local')

    def test_explicit_home_ignores_inherited_harness_overrides(self):
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.base / 'outside-claude'),
                   HERMES_HOME=str(self.base / 'outside-hermes'))
        self.run_cli('--apply', env=env)
        self.assertTrue(self.target().is_symlink())
        self.assertFalse((self.base / 'outside-claude').exists())
        self.assertFalse((self.base / 'outside-hermes').exists())

    def test_missing_source_is_reported_without_touching_destination(self):
        with self.manifest.open('a') as f:
            f.write('''[skills.missing]
source = "local:~/absent/missing"
harnesses = ["claude"]
pack = "default"
''')
        self.assertIn('UNAVAILABLE', self.run_cli('--plan').stdout)
        self.run_cli('--apply')
        self.assertFalse(self.target(name='missing').exists())

    def test_opt_in_pack_is_not_default(self):
        text = self.manifest.read_text().replace('pack = "default"', 'pack = "pstack"')
        self.manifest.write_text(text)
        self.run_cli('--apply')
        self.assertFalse(self.target().exists())
        self.run_cli('--apply', '--pack', 'pstack')
        self.assertTrue(self.target().is_symlink())

    def test_pinned_checkout_requires_exact_clean_commit(self):
        checkout = self.base / 'external'
        skill = checkout / 'skills/pinned'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('pinned skill')
        subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(checkout), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture' + '@' + 'example.invalid',
                        'commit', '-qm', 'fixture'], check=True)
        head = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
        with self.manifest.open('a') as f:
            f.write(f'[sources.external]\nrepository = "https://github.com/example/project"\n'
                    f'commit = "{head}"\ncheckout = "{checkout}"\n'
                    '[skills.pinned]\nsource = "git:external:skills/pinned"\n'
                    'harnesses = ["claude"]\npack = "default"\n')
        self.run_cli('--apply', '--harness', 'claude')
        self.assertEqual(self.target(name='pinned').resolve(), skill)
        self.run_cli('--uninstall')
        (skill / 'SKILL.md').write_text('locally changed')
        output = self.run_cli('--apply', '--harness', 'claude').stdout
        self.assertIn('UNAVAILABLE pinned', output)
        self.assertFalse(self.target(name='pinned').exists())
        (skill / 'SKILL.md').write_text('pinned skill')
        self.manifest.write_text(self.manifest.read_text().replace(head, '0' * 40))
        self.assertIn('UNAVAILABLE pinned', self.run_cli('--plan').stdout)

    def test_symlinked_harness_parent_has_one_physical_destination(self):
        real = self.home / 'shared-skills'
        real.mkdir()
        parent = self.home / '.agents'
        parent.mkdir()
        (parent / 'skills').symlink_to(real)
        self.run_cli('--apply', '--harness', 'codex')
        self.assertTrue((real / 'sample').is_symlink())
        self.run_cli('--apply', '--harness', 'agents')
        self.run_cli('--uninstall', '--harness', 'agents')
        self.assertTrue((parent / 'skills').is_symlink())
        self.assertFalse((real / 'sample').exists())

    def test_missing_owned_link_can_be_repaired_without_losing_original(self):
        target = self.target()
        target.mkdir(parents=True)
        (target / 'payload').write_bytes(b'original bytes')
        self.run_cli('--apply', '--harness', 'claude')
        target.unlink()
        self.run_cli('--apply', '--harness', 'claude')
        self.run_cli('--uninstall')
        self.assertEqual((target / 'payload').read_bytes(), b'original bytes')

    def test_manifest_path_escape_refused_before_mutation(self):
        self.manifest.write_text(self.manifest.read_text().replace('skills/sample', '../outside'))
        before = self.snapshot()
        self.assertIn('UNAVAILABLE sample', self.run_cli('--apply').stdout)
        self.assertEqual(before, self.snapshot())

    def test_private_overlay_is_local_and_opt_in(self):
        private = self.home / '.local/share/kvnloo-skills-private/skills/local-extra'
        private.mkdir(parents=True)
        (private / 'SKILL.md').write_text('private')
        self.run_cli('--apply', '--harness', 'claude')
        self.assertFalse(self.target(name='local-extra').exists())
        self.run_cli('--apply', '--harness', 'claude', '--private')
        self.assertEqual(self.target(name='local-extra').resolve(), private)


if __name__ == '__main__':
    unittest.main()

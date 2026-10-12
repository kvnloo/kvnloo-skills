"""Synthetic privacy fixtures never contain real private identifiers."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / 'scripts/check-public-safe'


class PublicSafeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)

    def check(self, content, *, name='sample.txt', extra=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        subprocess.run(['git', '-C', str(self.root), 'add', name], check=True)
        if extra:
            (self.root / '.public-safe-patterns.local').write_text(extra)
        return subprocess.run([str(CHECKER), '--root', str(self.root)],
                              capture_output=True, text=True)

    def test_clean_tree_passes(self):
        self.assertEqual(self.check('Portable skills and https://github.com/example/project').returncode, 0)

    def test_generic_sensitive_patterns_fail_without_echoing_value(self):
        values = ['/' + 'home' + '/example-person/secret', '/' + 'Users' + '/example-person/file',
                  'example-person' + '@' + 'example.invalid', 'sk-' + 'A' * 40,
                  'example-machine' + '.ts.net', '/' + 'workspace' + '/local-project/file']
        for value in values:
            with self.subTest(value=value):
                result = self.check(value)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertNotIn(value, result.stdout)

    def test_local_patterns_are_loaded_but_local_file_is_not_scanned(self):
        phrase = 'example-sensitive-project'
        result = self.check('See ' + phrase, extra=phrase + '\n')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(phrase, result.stdout)
        self.assertEqual(self.check('Portable content').returncode, 0)

    def test_sensitive_filename_and_symlink_target_fail(self):
        name = 'private' + '-example/SKILL.md'
        self.assertEqual(self.check('portable', name=name).returncode, 1)

    def test_checker_does_not_follow_links_outside_repo(self):
        self.check('portable')
        outside = self.root.parent / (self.root.name + '-not-read')
        outside.write_text('sk-' + 'Z' * 40)
        self.addCleanup(outside.unlink)
        link = self.root / 'link'
        link.symlink_to(outside)
        subprocess.run(['git', '-C', str(self.root), 'add', 'link'], check=True)
        # Absolute symlink targets are rejected without reading the target.
        result = subprocess.run([str(CHECKER), '--root', str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('symlink', result.stdout)


if __name__ == '__main__':
    unittest.main()

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


class PublicSafeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.env = os.environ.copy()
        self.env.update({
            'GIT_CONFIG_NOSYSTEM': '1',
            'GIT_CONFIG_GLOBAL': os.devnull,
            'GIT_AUTHOR_NAME': 'Fixture Author',
            'GIT_AUTHOR_EMAIL': 'fixture-author',
            'GIT_COMMITTER_NAME': 'Fixture Committer',
            'GIT_COMMITTER_EMAIL': 'fixture-committer',
            'GIT_AUTHOR_DATE': '2001-01-01T00:00:00+0000',
            'GIT_COMMITTER_DATE': '2001-01-01T00:00:00+0000',
        })
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, env=self.env)

    def git(self, *args, env=None):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True, env=env or self.env).stdout.strip()

    def commit(self, message='Fixture commit', *, env=None):
        self.git('add', '-A')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-q', '--allow-empty',
                 '-m', message, env=env)
        return self.git('rev-parse', 'HEAD')

    def scan(self, *refs, root=None):
        args = [str(CHECKER), '--root', str(root or self.root)]
        for ref in refs:
            args.extend(['--history', ref])
        return subprocess.run(args, capture_output=True, text=True, env=self.env)

    def assert_finding(self, result, value, object_id=None):
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 1, output)
        self.assertNotIn(value, output)
        if object_id:
            self.assertIn(object_id, output)

    def test_clean_history_and_current_tree_are_both_checked(self):
        path = self.root / 'sample.txt'
        path.write_text('Portable content\n')
        self.commit()
        result = self.scan('HEAD')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = 'sk-' + 'A' * 40
        path.write_text(value)
        self.assert_finding(self.scan('HEAD'), value)

    def test_removed_content_is_still_checked(self):
        value = 'sk-' + 'B' * 40
        path = self.root / 'sample.txt'
        path.write_text(value)
        self.commit()
        blob = self.git('rev-parse', 'HEAD:sample.txt')
        path.unlink()
        self.commit('Remove content')
        self.assertEqual(self.scan().returncode, 0)
        self.assert_finding(self.scan('HEAD'), value, blob)

    def test_removed_sensitive_filename_is_redacted(self):
        name = 'private' + '-fixture/SKILL.md'
        path = self.root / name
        path.parent.mkdir()
        path.write_text('Portable content\n')
        self.commit()
        path.unlink()
        self.commit('Remove file')
        self.assert_finding(self.scan('HEAD'), name)

    def test_removed_symlink_target_is_checked(self):
        value = 'private' + '-fixture-target'
        link = self.root / 'link'
        link.symlink_to(value)
        self.commit()
        blob = self.git('rev-parse', 'HEAD:link')
        link.unlink()
        self.commit('Remove link')
        self.assert_finding(self.scan('HEAD'), value, blob)

    def test_commit_message_and_author_metadata_are_checked(self):
        message_value = 'sk-' + 'C' * 40
        message_commit = self.commit('Fixture ' + message_value)
        self.assert_finding(self.scan('HEAD'), message_value, message_commit)
        email = 'fixture-author' + '@' + 'example.invalid'
        env = self.env.copy()
        env['GIT_AUTHOR_EMAIL'] = email
        metadata_commit = self.commit('Metadata fixture', env=env)
        self.assert_finding(self.scan('HEAD'), email, metadata_commit)

    def test_annotated_tag_message_and_tagger_metadata_are_checked(self):
        self.commit()
        value = 'sk-' + 'D' * 40
        email = 'fixture-tagger' + '@' + 'example.invalid'
        env = self.env.copy()
        env['GIT_COMMITTER_EMAIL'] = email
        self.git('-c', 'tag.gpgsign=false', 'tag', '-a', 'fixture-tag',
                 '-m', 'Fixture ' + value, env=env)
        tag_id = self.git('rev-parse', 'refs/tags/fixture-tag')
        self.assertEqual(self.scan('HEAD').returncode, 0)
        result = self.scan('refs/tags/fixture-tag')
        self.assert_finding(result, value, tag_id)
        self.assert_finding(result, email, tag_id)

    def test_local_literal_applies_to_history_without_disclosure(self):
        value = 'fixture-sensitive-identifier'
        path = self.root / 'sample.txt'
        path.write_text(value)
        self.commit()
        path.unlink()
        self.commit('Remove file')
        (self.root / '.public-safe-patterns.local').write_text(value + '\n')
        self.assert_finding(self.scan('HEAD'), value)

    def test_exact_refs_limit_scope_and_repeat_flags_union_it(self):
        clean = self.commit()
        self.git('branch', 'clean', clean)
        value = 'sk-' + 'E' * 40
        (self.root / 'sample.txt').write_text(value)
        bad = self.commit()
        self.git('branch', 'other', bad)
        self.git('checkout', '-q', '--detach', clean)
        result = self.scan('refs/heads/clean')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_finding(self.scan('refs/heads/clean', 'refs/heads/other'), value)

    def test_invalid_ref_is_error_without_disclosing_ref(self):
        self.commit()
        ref = 'private' + '-fixture-ref'
        result = self.scan(ref)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(ref, result.stdout + result.stderr)

    def test_shallow_history_is_error(self):
        self.commit()
        self.commit('Second commit')
        clone = Path(self.temp.name) / 'shallow'
        subprocess.run(['git', 'clone', '-q', '--depth', '1',
                        self.root.as_uri(), str(clone)], check=True,
                       capture_output=True, env=self.env)
        result = self.scan('HEAD', root=clone)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_missing_history_object_is_error(self):
        parent = self.commit()
        self.commit('Second commit')
        object_path = self.root / '.git' / 'objects' / parent[:2] / parent[2:]
        object_path.unlink()
        result = self.scan('HEAD')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_oversized_historical_blob_is_error(self):
        path = self.root / 'large.bin'
        path.write_bytes(b'x' * (16 * 1024 * 1024 + 1))
        self.commit()
        path.unlink()
        self.commit('Remove large file')
        result = self.scan('HEAD')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()

import os
import subprocess
import tempfile
import unittest

from vcstool.clients.git import GitClient
from vcstool.commands.fetch import main as fetch_main
from vcstool.crawler import find_repositories
from vcstool.util import rmtree


def _init_source_repo(path, name='demo'):
    os.makedirs(path)
    subprocess.check_call(
        ['git', 'init'], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ['git', 'config', 'user.email', 'test@example.com'], cwd=path)
    subprocess.check_call(
        ['git', 'config', 'user.name', 'test'], cwd=path)
    subprocess.check_call(
        ['git', 'symbolic-ref', 'HEAD', 'refs/heads/main'], cwd=path)
    with open(os.path.join(path, 'README'), 'w') as handle:
        handle.write(name + '\n')
    subprocess.check_call(
        ['git', 'add', 'README'], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ['git', 'commit', '-q', '-m', 'init'], cwd=path)
    return path


def _commit_file(path, filename, content, message):
    with open(os.path.join(path, filename), 'w') as handle:
        handle.write(content)
    subprocess.check_call(
        ['git', 'add', filename], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ['git', 'commit', '-q', '-m', message], cwd=path)


def _rev_parse(git_dir_or_worktree, ref, git_dir=False):
    cmd = ['git']
    cwd = git_dir_or_worktree
    if git_dir:
        cmd += ['--git-dir', git_dir_or_worktree]
        cwd = None
    cmd += ['rev-parse', ref]
    return subprocess.check_output(
        cmd, cwd=cwd, stderr=subprocess.DEVNULL).decode().strip()


def _ref_exists(git_dir, ref):
    try:
        _rev_parse(git_dir, ref, git_dir=True)
        return True
    except subprocess.CalledProcessError:
        return False


class TestFetch(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='vcstool-fetch-')
        self.addCleanup(rmtree, self.tmpdir)
        self.source = _init_source_repo(
            os.path.join(self.tmpdir, 'source'), 'source')
        self.workspace = os.path.join(self.tmpdir, 'ws')
        os.makedirs(self.workspace)
        self.worktree = os.path.join(self.workspace, 'work')
        self.mirror = os.path.join(self.workspace, 'mirror.git')
        self.bare = os.path.join(self.workspace, 'bare.git')
        subprocess.check_call(
            ['git', 'clone', '-q', self.source, self.worktree],
            stdout=subprocess.DEVNULL)
        subprocess.check_call(
            ['git', 'clone', '-q', '--mirror', self.source, self.mirror],
            stdout=subprocess.DEVNULL)
        subprocess.check_call(
            ['git', 'clone', '-q', '--bare', self.source, self.bare],
            stdout=subprocess.DEVNULL)

    def test_is_bare_skips_worktree_git_dir(self):
        self.assertTrue(GitClient.is_repository(self.worktree))
        self.assertFalse(GitClient.is_bare_repository(self.worktree))
        self.assertFalse(
            GitClient.is_bare_repository(os.path.join(self.worktree, '.git')))
        self.assertTrue(GitClient.is_bare_repository(self.mirror))
        self.assertTrue(GitClient.is_bare_repository(self.bare))

    def test_crawler_include_bare(self):
        found = find_repositories([self.workspace])
        self.assertEqual([client.path for client in found], [self.worktree])

        found = find_repositories([self.workspace], include_bare=True)
        paths = sorted(client.path for client in found)
        self.assertEqual(
            paths, sorted([self.worktree, self.mirror, self.bare]))

        found = find_repositories(
            [self.workspace], nested=True, include_bare=True)
        paths = [client.path for client in found]
        self.assertNotIn(os.path.join(self.worktree, '.git'), paths)
        self.assertEqual(len(paths), 3)

    def test_fetch_updates_worktree_and_mirrors(self):
        _commit_file(self.source, 'next.txt', 'n\n', 'second')
        subprocess.check_call(
            ['git', 'branch', 'feature'], cwd=self.source)
        subprocess.check_call(
            ['git', 'tag', 'v1'], cwd=self.source)
        source_head = _rev_parse(self.source, 'HEAD')

        rc = fetch_main([self.workspace, '--workers', '1'])
        self.assertEqual(rc, 0)

        self.assertEqual(
            _rev_parse(self.worktree, 'origin/main'), source_head)
        self.assertEqual(
            _rev_parse(self.mirror, 'refs/heads/main', git_dir=True),
            source_head)
        self.assertTrue(_ref_exists(self.mirror, 'refs/heads/feature'))
        self.assertTrue(_ref_exists(self.mirror, 'refs/tags/v1'))
        self.assertEqual(
            _rev_parse(self.bare, 'refs/heads/main', git_dir=True),
            source_head)
        self.assertTrue(_ref_exists(self.bare, 'refs/heads/feature'))
        self.assertTrue(_ref_exists(self.bare, 'refs/tags/v1'))

    def test_fetch_prunes_deleted_refs(self):
        subprocess.check_call(
            ['git', 'branch', 'gone'], cwd=self.source)
        rc = fetch_main([self.workspace, '--workers', '1'])
        self.assertEqual(rc, 0)
        self.assertTrue(_ref_exists(self.mirror, 'refs/heads/gone'))
        self.assertTrue(_ref_exists(self.bare, 'refs/heads/gone'))

        subprocess.check_call(
            ['git', 'branch', '-D', 'gone'], cwd=self.source)
        rc = fetch_main(
            [self.workspace, '--workers', '1', '--no-prune'])
        self.assertEqual(rc, 0)
        self.assertTrue(_ref_exists(self.mirror, 'refs/heads/gone'))

        rc = fetch_main([self.workspace, '--workers', '1'])
        self.assertEqual(rc, 0)
        self.assertFalse(_ref_exists(self.mirror, 'refs/heads/gone'))
        self.assertFalse(_ref_exists(self.bare, 'refs/heads/gone'))


if __name__ == '__main__':
    unittest.main()

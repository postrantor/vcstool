from io import StringIO
import os
import subprocess
import tempfile
import unittest

from vcstool.clients.git import GitClient
from vcstool.commands.import_ import main as import_main
from vcstool.repos_file import collect_from_directory
from vcstool.repos_file import collect_from_tree_file
from vcstool.repos_file import extract_tree_options
from vcstool.repos_file import resolve_clone_path
from vcstool.util import rmtree


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as handle:
        handle.write(content)


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


def _file_url(path):
    return 'file://' + os.path.abspath(path)


def _repos_entry(rel_path, url, version='main'):
    return (
        '  %s:\n'
        '    type: git\n'
        '    url: %s\n'
        '    version: %s\n' % (rel_path, url, version))


class TestTreeOptionSchema(unittest.TestCase):

    def test_extracts_all_import_fields(self):
        options = extract_tree_options({
            'manifest': 'child/child.repos',
            'bare': True,
            'mirror': True,
            'force': True,
            'shallow': False,
            'recursive': True,
            'skip_existing': True,
            'skip-existing': False,
            'retry': 3,
            'workers': 6,
            'debug': True,
            'repos': True,
            'verbose': True,
            'unknown': 'ignore',
        })
        self.assertEqual(options['bare'], True)
        self.assertEqual(options['mirror'], True)
        self.assertEqual(options['force'], True)
        self.assertEqual(options['shallow'], False)
        self.assertEqual(options['recursive'], True)
        self.assertEqual(options['skip_existing'], False)
        self.assertEqual(options['retry'], 3)
        self.assertEqual(options['workers'], 6)
        self.assertEqual(options['debug'], True)
        self.assertEqual(options['repos'], True)
        self.assertEqual(options['verbose'], True)
        self.assertNotIn('manifest', options)
        self.assertNotIn('unknown', options)


class TestResolveClonePath(unittest.TestCase):

    def test_bare_appends_git(self):
        self.assertEqual(
            resolve_clone_path('foo', '/tmp', True),
            os.path.join('/tmp', 'foo.git'))
        self.assertEqual(
            resolve_clone_path('abx/common', '/tmp', True),
            os.path.join('/tmp', 'abx/common.git'))

    def test_bare_keeps_existing_suffix(self):
        self.assertEqual(
            resolve_clone_path('foo.git', '/tmp', True),
            os.path.join('/tmp', 'foo.git'))

    def test_mirror_appends_git(self):
        self.assertEqual(
            resolve_clone_path('foo', '/tmp', False, mirror=True),
            os.path.join('/tmp', 'foo.git'))

    def test_non_bare_keeps_path(self):
        self.assertEqual(
            resolve_clone_path('foo', '/tmp', False),
            os.path.join('/tmp', 'foo'))
        self.assertEqual(
            resolve_clone_path('foo.git', '/tmp', False),
            os.path.join('/tmp', 'foo.git'))


class TestTreeCollect(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='vcstool-tree-')
        self.addCleanup(rmtree, self.tmpdir)

    def test_tree_and_directory_scan(self):
        root = os.path.join(self.tmpdir, 'root.repos')
        child = os.path.join(self.tmpdir, 'child', 'child.repos')
        sibling = os.path.join(self.tmpdir, 'sibling', 'sibling.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n')
        _write(
            child,
            'repositories:\n' +
            _repos_entry('foo', 'file:///tmp/foo'))
        _write(
            sibling,
            'repositories:\n' +
            _repos_entry('bar', 'file:///tmp/bar'))

        hidden_bare = os.path.join(self.tmpdir, 'skip.git', 'hidden.repos')
        _write(
            hidden_bare,
            'repositories:\n' +
            _repos_entry('hidden', 'file:///tmp/hidden'))
        worktree = os.path.join(self.tmpdir, 'worktree', '.git')
        os.makedirs(worktree)
        _write(
            os.path.join(self.tmpdir, 'worktree', 'hidden.repos'),
            'repositories:\n' +
            _repos_entry('hidden2', 'file:///tmp/hidden2'))

        groups = collect_from_tree_file(root)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], os.path.dirname(child))
        self.assertIn('foo', groups[0][1])

        found = collect_from_directory(self.tmpdir)
        paths = {name for _base, repos, _opts in found for name in repos}
        self.assertIn('foo', paths)
        self.assertNotIn('bar', paths)
        self.assertNotIn('hidden', paths)
        self.assertNotIn('hidden2', paths)

    def test_tree_manifest_and_filter(self):
        root = os.path.join(self.tmpdir, 'root.repos')
        child = os.path.join(self.tmpdir, 'child', 'child.repos')
        sibling = os.path.join(self.tmpdir, 'sibling', 'sibling.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            '    mirror: true\n'
            '    force: true\n'
            '    workers: 6\n'
            '  sibling:\n'
            '    manifest: sibling/sibling.repos\n'
            '    mirror: false\n')
        _write(
            child,
            'repositories:\n' +
            _repos_entry('foo', 'file:///tmp/foo'))
        _write(
            sibling,
            'repositories:\n' +
            _repos_entry('bar', 'file:///tmp/bar'))

        groups = collect_from_tree_file(root)
        self.assertEqual(len(groups), 2)
        by_base = {base: (repos, opts) for base, repos, opts in groups}
        self.assertTrue(by_base[os.path.dirname(child)][1]['mirror'])
        self.assertEqual(by_base[os.path.dirname(child)][1]['workers'], 6)
        self.assertFalse(by_base[os.path.dirname(sibling)][1]['mirror'])

        filtered = collect_from_tree_file(root, manifest_names=['child'])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0][0], os.path.dirname(child))

    def test_tree_ignores_local_repositories(self):
        root = os.path.join(self.tmpdir, 'mixed.repos')
        child = os.path.join(self.tmpdir, 'child', 'child.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            'repositories:\n' +
            _repos_entry('local', 'file:///tmp/local'))
        _write(
            child,
            'repositories:\n' +
            _repos_entry('foo', 'file:///tmp/foo'))
        groups = collect_from_tree_file(root)
        paths = {name for _base, repos, _opts in groups for name in repos}
        self.assertEqual(paths, {'foo'})

    def test_cycle_and_missing(self):
        a = os.path.join(self.tmpdir, 'a.repos')
        b = os.path.join(self.tmpdir, 'b.repos')
        _write(
            a,
            'tree:\n'
            '  b:\n'
            '    manifest: b.repos\n')
        _write(
            b,
            'tree:\n'
            '  a:\n'
            '    manifest: a.repos\n')
        with self.assertRaises(RuntimeError) as ctx:
            collect_from_tree_file(a)
        self.assertIn('Cyclic tree', str(ctx.exception))

        missing = os.path.join(self.tmpdir, 'missing.repos')
        _write(
            missing,
            'tree:\n'
            '  gone:\n'
            '    manifest: no-such.repos\n')
        with self.assertRaises(RuntimeError) as ctx:
            collect_from_tree_file(missing)
        self.assertIn('Manifest not found', str(ctx.exception))


class TestTreeImport(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='vcstool-import-')
        self.addCleanup(rmtree, self.tmpdir)
        self.foo = _init_source_repo(
            os.path.join(self.tmpdir, 'src', 'foo'), 'foo')
        self.bar = _init_source_repo(
            os.path.join(self.tmpdir, 'src', 'bar'), 'bar')

    def _run_import(self, args):
        rc = import_main(args)
        self.assertEqual(rc, 0, 'import failed: %s' % args)

    def test_bare_suffix_from_input(self):
        dest = os.path.join(self.tmpdir, 'dest-bare')
        os.makedirs(dest)
        repos = os.path.join(self.tmpdir, 'single.repos')
        _write(
            repos,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(
            ['--input', repos, '--bare', dest])
        cloned = os.path.join(dest, 'foo.git')
        self.assertTrue(GitClient.is_bare_repository(cloned))
        self.assertFalse(os.path.exists(os.path.join(dest, 'foo')))

    def test_mirror_suffix_from_input(self):
        dest = os.path.join(self.tmpdir, 'dest-mirror')
        os.makedirs(dest)
        repos = os.path.join(self.tmpdir, 'single-mirror.repos')
        _write(
            repos,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(
            ['--input', repos, '--mirror', dest])
        cloned = os.path.join(dest, 'foo.git')
        self.assertTrue(GitClient.is_bare_repository(cloned))
        self.assertEqual(
            subprocess.check_output(
                ['git', 'config', '--get', 'remote.origin.mirror'],
                cwd=cloned).decode().strip(),
            'true')

    def test_mirror_wins_over_bare(self):
        dest = os.path.join(self.tmpdir, 'dest-both')
        os.makedirs(dest)
        repos = os.path.join(self.tmpdir, 'single-both.repos')
        _write(
            repos,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(
            ['--input', repos, '--bare', '--mirror', dest])
        cloned = os.path.join(dest, 'foo.git')
        self.assertEqual(
            subprocess.check_output(
                ['git', 'config', '--get', 'remote.origin.mirror'],
                cwd=cloned).decode().strip(),
            'true')

    def test_non_bare_keeps_key(self):
        dest = os.path.join(self.tmpdir, 'dest-worktree')
        os.makedirs(dest)
        repos = os.path.join(self.tmpdir, 'single.repos')
        _write(
            repos,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(['--input', repos, dest])
        cloned = os.path.join(dest, 'foo')
        self.assertTrue(GitClient.is_repository(cloned))
        self.assertFalse(os.path.exists(os.path.join(dest, 'foo.git')))

    def test_bare_does_not_double_suffix(self):
        dest = os.path.join(self.tmpdir, 'dest-suffix')
        os.makedirs(dest)
        repos = os.path.join(self.tmpdir, 'already.repos')
        _write(
            repos,
            'repositories:\n' +
            _repos_entry('foo.git', _file_url(self.foo)))
        self._run_import(
            ['--input', repos, '--bare', dest])
        self.assertTrue(
            GitClient.is_bare_repository(os.path.join(dest, 'foo.git')))
        self.assertFalse(os.path.exists(os.path.join(dest, 'foo.git.git')))

    def test_tree_file_imports_in_place(self):
        workspace = os.path.join(self.tmpdir, 'ws')
        child_dir = os.path.join(workspace, 'child')
        root = os.path.join(workspace, 'root.repos')
        child = os.path.join(child_dir, 'child.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            '    mirror: true\n')
        _write(
            child,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(['--tree', root])
        cloned = os.path.join(child_dir, 'foo.git')
        self.assertTrue(GitClient.is_bare_repository(cloned))
        self.assertFalse(
            os.path.exists(os.path.join(workspace, 'foo.git')))

    def test_manifest_intersection(self):
        workspace = os.path.join(self.tmpdir, 'ws')
        child_dir = os.path.join(workspace, 'child')
        sibling_dir = os.path.join(workspace, 'sibling')
        root = os.path.join(workspace, 'root.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            '    mirror: true\n'
            '  sibling:\n'
            '    manifest: sibling/sibling.repos\n'
            '    mirror: true\n')
        _write(
            os.path.join(child_dir, 'child.repos'),
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        _write(
            os.path.join(sibling_dir, 'sibling.repos'),
            'repositories:\n' +
            _repos_entry('bar', _file_url(self.bar)))
        self._run_import(['--tree', root, '--manifests', 'child'])
        self.assertTrue(
            GitClient.is_bare_repository(os.path.join(child_dir, 'foo.git')))
        self.assertFalse(
            os.path.exists(os.path.join(sibling_dir, 'bar.git')))

    def test_tree_config_overrides_cli_bare(self):
        workspace = os.path.join(self.tmpdir, 'ws')
        child_dir = os.path.join(workspace, 'child')
        root = os.path.join(workspace, 'root.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            '    bare: false\n')
        _write(
            os.path.join(child_dir, 'child.repos'),
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(['--tree', root, '--bare'])
        cloned = os.path.join(child_dir, 'foo')
        self.assertTrue(GitClient.is_repository(cloned))
        self.assertFalse(os.path.exists(cloned + '.git'))

    def test_tree_directory_follows_tree_only(self):
        workspace = os.path.join(self.tmpdir, 'scan')
        root = os.path.join(workspace, 'root.repos')
        child = os.path.join(workspace, 'child', 'child.repos')
        sibling = os.path.join(workspace, 'sibling', 'sibling.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            '    mirror: true\n')
        _write(
            child,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        _write(
            sibling,
            'repositories:\n' +
            _repos_entry('bar', _file_url(self.bar)))
        self._run_import(['--tree', workspace])
        self.assertTrue(
            GitClient.is_bare_repository(
                os.path.join(workspace, 'child', 'foo.git')))
        self.assertFalse(
            os.path.exists(os.path.join(workspace, 'sibling', 'bar.git')))

    def test_input_ignores_tree(self):
        dest = os.path.join(self.tmpdir, 'dest-input')
        os.makedirs(dest)
        repos = os.path.join(self.tmpdir, 'mixed.repos')
        _write(
            repos,
            'tree:\n'
            '  child:\n'
            '    manifest: missing.repos\n'
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(['--input', repos, dest])
        self.assertTrue(GitClient.is_repository(os.path.join(dest, 'foo')))

    def test_tree_ignores_mixed_repositories(self):
        workspace = os.path.join(self.tmpdir, 'mixed-ws')
        root = os.path.join(workspace, 'mixed.repos')
        child = os.path.join(workspace, 'child', 'child.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            '    mirror: true\n'
            'repositories:\n' +
            _repos_entry('local', _file_url(self.bar)))
        _write(
            child,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        self._run_import(['--tree', root])
        cloned = os.path.join(workspace, 'child', 'foo.git')
        self.assertTrue(GitClient.is_bare_repository(cloned))
        self.assertFalse(os.path.exists(os.path.join(workspace, 'local.git')))
        self.assertFalse(os.path.exists(os.path.join(workspace, 'local')))

    def test_tree_rejects_input(self):
        repos = os.path.join(self.tmpdir, 'single.repos')
        _write(repos, 'repositories: {}\n')
        rc = import_main(['--tree', repos, '--input', repos])
        self.assertEqual(rc, 1)

    def test_manifests_requires_tree(self):
        rc = import_main(['--manifests', 'child'])
        self.assertEqual(rc, 1)

    def test_tree_cycle_returns_error(self):
        a = os.path.join(self.tmpdir, 'a.repos')
        b = os.path.join(self.tmpdir, 'b.repos')
        _write(
            a,
            'tree:\n'
            '  b:\n'
            '    manifest: b.repos\n')
        _write(
            b,
            'tree:\n'
            '  a:\n'
            '    manifest: a.repos\n')
        rc = import_main(['--tree', a])
        self.assertEqual(rc, 1)

    def test_verbose_prints_yaml_progress(self):
        dest = os.path.join(self.tmpdir, 'dest-verbose')
        os.makedirs(dest)
        repos = os.path.join(self.tmpdir, 'verbose.repos')
        _write(
            repos,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)) +
            _repos_entry('bar', _file_url(self.bar)))
        buf = StringIO()
        rc = import_main(
            ['--input', repos, '--verbose', '--workers', '1', dest],
            stdout=buf, stderr=buf)
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn('- progress: 1/2', text)
        self.assertIn('- progress: 2/2', text)
        self.assertIn('result: ok', text)
        self.assertIn('type: git', text)
        self.assertIn(_file_url(self.foo), text)
        self.assertIn(os.path.join(dest, 'foo'), text)
        self.assertIn(os.path.join(dest, 'bar'), text)
        self.assertNotRegex(text, r'(?m)^\.\.$')

    def test_verbose_from_tree_option(self):
        workspace = os.path.join(self.tmpdir, 'verbose-tree')
        root = os.path.join(workspace, 'root.repos')
        child = os.path.join(workspace, 'child', 'child.repos')
        _write(
            root,
            'tree:\n'
            '  child:\n'
            '    manifest: child/child.repos\n'
            '    mirror: true\n'
            '    verbose: true\n')
        _write(
            child,
            'repositories:\n' +
            _repos_entry('foo', _file_url(self.foo)))
        buf = StringIO()
        rc = import_main(['--tree', root, '--workers', '1'], stdout=buf)
        self.assertEqual(rc, 0)
        text = buf.getvalue()
        self.assertIn('- progress: 1/1', text)
        self.assertIn('result: ok', text)
        self.assertIn(
            os.path.join(workspace, 'child', 'foo.git'), text)


if __name__ == '__main__':
    unittest.main()

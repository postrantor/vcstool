import os
import sys

from vcstool.executor import ansi
import yaml


TREE_OPTION_KEYS = {
    'bare',
    'debug',
    'force',
    'mirror',
    'recursive',
    'repos',
    'retry',
    'shallow',
    'skip_existing',
    'verbose',
    'workers',
}

TREE_OPTION_ALIASES = {
    'skip-existing': 'skip_existing',
}


def resolve_clone_path(rel_path, dest_base, bare, mirror=False):
    rel_path = rel_path.rstrip('/\\')
    if (bare or mirror) and not rel_path.endswith('.git'):
        rel_path = rel_path + '.git'
    return os.path.join(dest_base, rel_path)


def merge_options(*layers):
    merged = {}
    for layer in layers:
        if layer:
            merged.update(layer)
    return merged


def get_repositories(yaml_file):
    root = _load_yaml(yaml_file)

    if isinstance(root, dict) and 'repositories' in root:
        return get_repos_in_vcstool_format(root['repositories'])

    if isinstance(root, dict) and root.get('tree'):
        raise RuntimeError(
            "Input lists a 'tree'; use 'vcs import --tree'")

    try:
        return get_repos_in_rosinstall_format(root)
    except (AttributeError, KeyError, RuntimeError, TypeError) as e:
        raise RuntimeError('Input data is not valid format: %s' % e)


def load_repos_document(path):
    with open(path, 'r') as handle:
        root = _load_yaml(handle)

    if root is None:
        return {
            'path': path,
            'tree': {},
            'repositories': {},
            'options': {},
        }

    if not isinstance(root, dict):
        return {
            'path': path,
            'tree': {},
            'repositories': get_repos_in_rosinstall_format(root),
            'options': {},
        }

    tree = _parse_tree(root)
    options = extract_tree_options(root)
    if 'repositories' in root:
        repos = get_repos_in_vcstool_format(root['repositories'])
    else:
        repos = {}
    if not tree and not repos and 'repositories' not in root:
        raise RuntimeError(
            "Input data is not valid format: missing 'tree' or repositories")
    return {
        'path': path,
        'tree': tree,
        'repositories': repos,
        'options': options,
    }


def extract_tree_options(mapping):
    options = {}
    if not isinstance(mapping, dict):
        return options
    for key, value in mapping.items():
        name = TREE_OPTION_ALIASES.get(key, key)
        if name not in TREE_OPTION_KEYS:
            continue
        if name in (
            'bare', 'debug', 'force', 'mirror', 'recursive', 'repos',
            'shallow', 'skip_existing', 'verbose'
        ):
            options[name] = bool(value)
        elif name in ('retry', 'workers'):
            options[name] = int(value)
        else:
            options[name] = value
    return options


def collect_from_tree(path, manifest_names=None):
    groups = []
    visited = set()
    stack = []
    names = set(manifest_names) if manifest_names else None
    matched = set()

    if os.path.isdir(path):
        tree_files = [
            item for item in find_repos_files(path)
            if _document_has_tree(item)]
        if not tree_files:
            raise RuntimeError(
                "No .repos file with a 'tree' field found under '%s'" % path)
        for item in tree_files:
            _collect_document(
                item, names, visited, stack, groups, matched,
                inherited=None, selected=False)
    elif os.path.isfile(path):
        doc = load_repos_document(path)
        if not doc['tree']:
            raise RuntimeError(
                "File '%s' has no 'tree' field; use --input" % path)
        _collect_document(
            path, names, visited, stack, groups, matched,
            inherited=None, selected=False)
    else:
        raise RuntimeError("Path '%s' is not a file or directory" % path)

    if names is not None:
        unknown = sorted(names - matched)
        if unknown:
            print(
                ansi('yellowf') +
                'No tree named: %s' % ', '.join(unknown) +
                ansi('reset'),
                file=sys.stderr)
        if not groups:
            raise RuntimeError(
                'No tree matched --manifests: %s' % ', '.join(sorted(names)))
    return groups


def collect_from_tree_file(path, manifest_names=None):
    return collect_from_tree(path, manifest_names=manifest_names)


def collect_from_directory(root, manifest_names=None):
    return collect_from_tree(root, manifest_names=manifest_names)


def find_repos_files(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False
    ):
        dirnames[:] = sorted(
            name for name in dirnames
            if not _should_skip_dir(dirpath, name))
        for name in sorted(filenames):
            if name.endswith('.repos'):
                found.append(os.path.join(dirpath, name))
    return found


def get_repos_in_vcstool_format(repositories):
    repos = {}
    if repositories is None:
        print(
            ansi('yellowf') + 'List of repositories is empty' + ansi('reset'),
            file=sys.stderr)
        return repos
    for path in repositories:
        repo = {}
        attributes = repositories[path]
        try:
            repo['type'] = attributes['type']
            repo['url'] = attributes['url']
            if 'version' in attributes:
                repo['version'] = attributes['version']
        except TypeError:
            print(
                ansi('yellowf') + (
                    "Repository '%s' does not provide the necessary "
                    'information: attributes must be a mapping' % path) +
                ansi('reset'),
                file=sys.stderr)
            continue
        except KeyError as e:
            print(
                ansi('yellowf') + (
                    "Repository '%s' does not provide the necessary "
                    'information: %s' % (path, e)) + ansi('reset'),
                file=sys.stderr)
            continue
        repos[path] = repo
    return repos


def get_repos_in_rosinstall_format(root):
    repos = {}
    for i, item in enumerate(root):
        if len(item.keys()) != 1:
            raise RuntimeError('Input data is not valid format')
        repo = {'type': list(item.keys())[0]}
        attributes = list(item.values())[0]
        try:
            path = attributes['local-name']
        except KeyError as e:
            print(
                ansi('yellowf') + (
                    'Repository #%d does not provide the necessary '
                    'information: %s' % (i, e)) + ansi('reset'),
                file=sys.stderr)
            continue
        try:
            repo['url'] = attributes['uri']
            if 'version' in attributes:
                repo['version'] = attributes['version']
        except KeyError as e:
            print(
                ansi('yellowf') + (
                    "Repository '%s' does not provide the necessary "
                    'information: %s' % (path, e)) + ansi('reset'),
                file=sys.stderr)
            continue
        repos[path] = repo
    return repos


def _collect_document(
    path, names, visited, stack, groups, matched, inherited, selected
):
    path = os.path.abspath(path)
    if path in stack:
        cycle = ' -> '.join(stack + [path])
        raise RuntimeError('Cyclic tree: %s' % cycle)
    if path in visited:
        return
    if not os.path.isfile(path):
        raise RuntimeError("Manifest not found: '%s'" % path)

    doc = load_repos_document(path)
    options = merge_options(inherited, doc['options'])
    stack.append(path)
    try:
        if doc['tree']:
            _follow_tree(
                path, doc, names, visited, stack, groups, matched, options)
        elif selected and doc['repositories']:
            groups.append((
                os.path.dirname(path), doc['repositories'], options))
    finally:
        stack.pop()
    if selected or doc['tree']:
        visited.add(path)


def _follow_tree(
    path, doc, names, visited, stack, groups, matched, options
):
    for name, spec in doc['tree'].items():
        if names is not None and name in names:
            matched.add(name)
        child = os.path.normpath(
            os.path.join(os.path.dirname(path), spec['manifest']))
        child_options = merge_options(options, spec['options'])
        name_selected = names is None or name in names
        if name_selected:
            _collect_document(
                child, None, visited, stack, groups, matched,
                inherited=child_options, selected=True)
        elif names is not None:
            _collect_document(
                child, names, visited, stack, groups, matched,
                inherited=child_options, selected=False)


def _parse_tree(root):
    tree = {}
    raw = root.get('tree')
    if raw is None:
        return tree
    if not isinstance(raw, dict):
        raise RuntimeError(
            "Input data is not valid format: 'tree' must be a mapping")
    for name, spec in raw.items():
        if spec is None:
            spec = {}
        if not isinstance(spec, dict):
            raise RuntimeError(
                'Input data is not valid format: tree.%s must be a mapping'
                % name)
        manifest = spec.get('manifest')
        if not manifest or not isinstance(manifest, str):
            raise RuntimeError(
                'Input data is not valid format: tree.%s must provide '
                "a string 'manifest'" % name)
        tree[name] = {
            'manifest': manifest,
            'options': extract_tree_options(spec),
        }
    return tree


def _document_has_tree(path):
    try:
        doc = load_repos_document(path)
    except (RuntimeError, OSError):
        return False
    return bool(doc['tree'])


def _load_yaml(yaml_file):
    try:
        return yaml.safe_load(yaml_file)
    except yaml.YAMLError as e:
        raise RuntimeError('Input data is not valid yaml format: %s' % e)


def _should_skip_dir(dirpath, name):
    if name == '.git' or name.endswith('.git'):
        return True
    return os.path.isdir(os.path.join(dirpath, name, '.git'))

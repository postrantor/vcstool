import argparse
import copy
import os
from shutil import which
import sys
import urllib.request as request

from vcstool import __version__ as vcstool_version
from vcstool.clients import vcstool_clients
from vcstool.clients.vcs_base import run_command
from vcstool.executor import ansi
from vcstool.executor import execute_jobs
from vcstool.executor import output_repositories
from vcstool.executor import output_results
from vcstool.repos_file import collect_from_tree
from vcstool.repos_file import get_repositories
from vcstool.repos_file import resolve_clone_path
from vcstool.streams import set_streams

from .command import add_common_arguments
from .command import Command


class ImportCommand(Command):

    command = 'import'
    help = 'Import the list of repositories'

    def __init__(
        self, args, url, version=None, recursive=False, shallow=False
    ):
        super(ImportCommand, self).__init__(args)
        self.url = url
        self.version = version
        self.force = args.force
        self.retry = args.retry
        self.skip_existing = args.skip_existing
        self.recursive = recursive
        self.shallow = shallow
        self.mirror = bool(getattr(args, 'mirror', False))
        self.bare = bool(getattr(args, 'bare', False))
        if self.mirror:
            self.bare = False


def get_parser():
    parser = argparse.ArgumentParser(
        description='Import the list of repositories', prog='vcs import')
    group = parser.add_argument_group('"import" command parameters')
    group.add_argument(
        '--input', type=file_or_url_type, default=None,
        help='Where to read YAML from (default: stdin). '
             'Cannot be used with --tree',
        metavar='FILE_OR_URL')
    group.add_argument(
        '--tree', type=tree_path_type, default=None, metavar='PATH',
        help='Import nested .repos via the tree field only. '
             'PATH may be a tree file (follows tree.<name>.manifest) '
             'or a directory. repositories in tree files are ignored. '
             'Cannot be used with --input')
    group.add_argument(
        '--manifests', nargs='+', metavar='NAME', default=None,
        help='Only import tree entries whose names intersect this list. '
             'Requires --tree')
    group.add_argument(
        '--force', action='store_true', default=False,
        help="Delete existing directories if they don't contain the "
             'repository being imported')
    group.add_argument(
        '--shallow', action='store_true', default=False,
        help='Create a shallow clone without a history')
    group.add_argument(
        '--bare', action='store_true', default=False,
        help='Create a bare clone and append .git to the destination '
             'path if it is missing. Overridden by --mirror')
    group.add_argument(
        '--mirror', action='store_true', default=False,
        help='Create a mirror clone (implies bare, fetches all refs) '
             'and append .git to the destination path if it is missing. '
             'Takes precedence over --bare')
    group.add_argument(
        '--recursive', action='store_true', default=False,
        help='Recurse into submodules')
    group.add_argument(
        '--retry', type=int, metavar='N', default=2,
        help='Retry commands requiring network access N times on failure')
    group.add_argument(
        '--skip-existing', action='store_true', default=False,
        help="Don't overwrite existing directories or change custom checkouts "
             'in repos using the same URL (but fetch repos with same URL)')

    return parser


def file_or_url_type(value):
    if os.path.exists(value) or '://' not in value:
        return argparse.FileType('r')(value)
    # use another user agent to avoid getting a 403 (forbidden) error,
    # since some websites blacklist or block unrecognized user agents
    return request.Request(
        value, headers={'User-Agent': 'vcstool/' + vcstool_version})


def tree_path_type(value):
    if not os.path.exists(value):
        raise argparse.ArgumentTypeError("Path '%s' does not exist." % value)
    if not os.path.isdir(value) and not os.path.isfile(value):
        raise argparse.ArgumentTypeError(
            "Path '%s' is not a file or directory." % value)
    return value


def _overlay_args(args, options):
    if not options:
        return args
    merged = copy.copy(args)
    for key, value in options.items():
        setattr(merged, key, value)
    return merged


def generate_jobs(repos, args, dest_base=None):
    jobs = []
    if dest_base is None:
        dest_base = args.path
    bare = bool(getattr(args, 'bare', False))
    mirror = bool(getattr(args, 'mirror', False))
    for path, repo in repos.items():
        path = resolve_clone_path(path, dest_base, bare, mirror=mirror)
        clients = [c for c in vcstool_clients if c.type == repo['type']]
        if not clients:
            from vcstool.clients.none import NoneClient
            job = {
                'client': NoneClient(path),
                'command': None,
                'cwd': path,
                'output':
                    "Repository type '%s' is not supported" % repo['type'],
                'returncode': NotImplemented
            }
            jobs.append(job)
            continue

        client = clients[0](path)
        command = ImportCommand(
            args, repo['url'],
            str(repo['version']) if 'version' in repo else None,
            recursive=args.recursive, shallow=args.shallow)
        job = {'client': client, 'command': command}
        jobs.append(job)
    return jobs


def add_dependencies(jobs):
    paths = [job['client'].path for job in jobs]
    for job in jobs:
        job['depends'] = set()
        path = job['client'].path
        while True:
            parent_path = os.path.dirname(path)
            if parent_path == path:
                break
            path = parent_path
            if path in paths:
                job['depends'].add(path)


def main(args=None, stdout=None, stderr=None):
    set_streams(stdout=stdout, stderr=stderr)

    parser = get_parser()
    add_common_arguments(
        parser, skip_hide_empty=True, skip_nested=True, path_nargs='?',
        path_help='Base path to clone repositories to')
    parsed = parser.parse_args(args)
    if parsed.tree and parsed.input is not None:
        print(
            ansi('redf') +
            '--tree and --input cannot be used together' +
            ansi('reset'),
            file=sys.stderr)
        return 1
    if parsed.manifests and not parsed.tree:
        print(
            ansi('redf') +
            '--manifests requires --tree' +
            ansi('reset'),
            file=sys.stderr)
        return 1

    try:
        if parsed.tree:
            jobs = []
            tree_workers = []
            tree_verbose = False
            for base_dir, repos, options in collect_from_tree(
                parsed.tree, manifest_names=parsed.manifests
            ):
                tree_args = _overlay_args(parsed, options)
                if 'workers' in options:
                    tree_workers.append(options['workers'])
                if options.get('verbose'):
                    tree_verbose = True
                jobs.extend(
                    generate_jobs(repos, tree_args, dest_base=base_dir))
            if tree_workers:
                parsed.workers = max(tree_workers)
            if tree_verbose:
                parsed.verbose = True
        else:
            input_ = parsed.input
            if input_ is None:
                input_ = argparse.FileType('r')('-')
            if isinstance(input_, request.Request):
                input_ = request.urlopen(input_)
            repos = get_repositories(input_)
            jobs = generate_jobs(repos, parsed)
    except (RuntimeError, request.URLError, OSError) as e:
        print(ansi('redf') + str(e) + ansi('reset'), file=sys.stderr)
        return 1
    add_dependencies(jobs)

    if parsed.repos:
        output_repositories([job['client'] for job in jobs])

    workers = parsed.workers
    # for ssh URLs check if the host is known to prevent ssh asking for
    # confirmation when using more than one worker
    if workers > 1:
        ssh_keygen = None
        checked_hosts = set()
        for job in list(jobs):
            if job['command'] is None:
                continue
            url = job['command'].url
            # only check the host from a ssh URL
            if not url.startswith('git@') or ':' not in url:
                continue
            host = url[4:].split(':', 1)[0]

            # only check each host name once
            if host in checked_hosts:
                continue
            checked_hosts.add(host)

            # get ssh-keygen path once
            if ssh_keygen is None:
                ssh_keygen = which('ssh-keygen') or False
            if not ssh_keygen:
                continue

            result = run_command([ssh_keygen, '-F', host], '')
            if result['returncode']:
                print(
                    'At least one hostname (%s) is unknown, switching to a '
                    'single worker to allow interactively answering the ssh '
                    'question to confirm the fingerprint' % host)
                workers = 1
                break

    results = execute_jobs(
        jobs, show_progress=True, number_of_workers=workers,
        debug_jobs=parsed.debug, verbose_progress=parsed.verbose)
    output_results(results)

    any_error = any(r['returncode'] for r in results)
    return 1 if any_error else 0


if __name__ == '__main__':
    sys.exit(main())

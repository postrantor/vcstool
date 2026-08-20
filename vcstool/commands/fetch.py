import argparse
import sys

from vcstool.streams import set_streams

from .command import Command
from .command import simple_main


class FetchCommand(Command):

    command = 'fetch'
    help = 'Fetch updates from remotes (work trees, bare, and mirrors)'

    def __init__(self, args):
        super(FetchCommand, self).__init__(args)
        self.include_bare = True
        self.prune = not args.no_prune


def get_parser():
    parser = argparse.ArgumentParser(
        description='Fetch updates from remotes for work trees, bare '
                    'repositories, and mirrors',
        prog='vcs fetch')
    group = parser.add_argument_group('"fetch" command parameters')
    group.add_argument(
        '--no-prune', action='store_true', default=False,
        help='Do not prune stale remote refs')
    return parser


def main(args=None, stdout=None, stderr=None):
    set_streams(stdout=stdout, stderr=stderr)
    parser = get_parser()
    return simple_main(parser, FetchCommand, args)


if __name__ == '__main__':
    sys.exit(main())

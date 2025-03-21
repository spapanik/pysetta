import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from pysetta.__version__ import __version__

sys.tracebacklimit = 0


def parse_args() -> Namespace:
    parser = ArgumentParser(prog="pysetta", description="Universal translator")
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="print the version and exit",
    )

    parent_parser = ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        default=False,
        help="do not write to the output file",
    )
    parent_parser.add_argument(
        "-l",
        "--language",
        action="append",
        dest="languages",
        default=[],
        help="languages to use for translation (default: all languages in the config)",
    )
    parent_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbosity",
        help="increase the level of verbosity",
    )
    parent_parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="path to the template file",
        default=None,
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser("generate", parents=[parent_parser])
    subparsers.add_parser("translate", parents=[parent_parser])

    args = parser.parse_args()
    if args.verbosity > 0:
        sys.tracebacklimit = 1000

    paths: set[Path] = set()
    for template in args.paths:
        if template.is_dir():
            paths.update(
                file.resolve() for file in template.rglob("*") if file.is_file()
            )
        else:
            paths.add(template.resolve())

    if not paths:
        msg = "No paths found. Please provide at least one template."
        raise ValueError(msg)

    args.paths = sorted(paths)

    return args

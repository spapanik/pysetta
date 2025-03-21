from __future__ import annotations

from pysetta.lib.cli import parse_args
from pysetta.lib.command import Command


def main() -> None:
    args = parse_args()
    command = Command(args.paths, args.languages, args.verbosity, dry_run=args.dry_run)
    match args.subcommand:
        case "generate":
            command.generate()
        case "translate":
            command.translate()
        case _:
            msg = f"Unknown subcommand: {args.subcommand}"
            raise ValueError(msg)

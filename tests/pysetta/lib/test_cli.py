from unittest import mock

import pytest

from pysetta.lib.cli import parse_args


@pytest.mark.parametrize("subcommand", ["generate", "translate"])
def test_verbosity(subcommand: str) -> None:
    with mock.patch("sys.argv", ["pysetta", subcommand, "templates/"]):
        args = parse_args()
        assert args.verbosity == 0

    with mock.patch("sys.argv", ["pysetta", subcommand, "-v", "templates/"]):
        args = parse_args()
        assert args.verbosity == 1

    with mock.patch("sys.argv", ["pysetta", subcommand, "-vvv", "templates/"]):
        args = parse_args()
        assert args.verbosity == 3

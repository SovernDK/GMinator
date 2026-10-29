"""Command-line entry point."""

import argparse
from collections.abc import Sequence

from gminator import __version__


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="gminator")
    parser.add_argument("--version", action="version", version=f"gminator {__version__}")
    parser.parse_args(argv)

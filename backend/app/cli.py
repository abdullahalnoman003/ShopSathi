"""Command entry point: python -m app.cli <command>. Later prompts add commands (e.g. seed)."""

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ShopSathi commands")
    parser.add_subparsers(dest="command", metavar="<command>")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

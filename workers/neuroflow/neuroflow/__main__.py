"""Argv-only CLI entry for the NeuroFlow worker.

Invoked as: python -m neuroflow <command> [args...]

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: AGPL-3.0-or-later
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neuroflow",
        description="NeuroFlow FOSS EEG preprocessing worker",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    ping = subparsers.add_parser(
        "ping",
        help="Health check; prints a JSON status object",
    )
    ping.set_defaults(handler=cmd_ping)

    return parser


def cmd_ping(_args: argparse.Namespace) -> int:
    payload = {
        "ok": True,
        "worker": "neuroflow",
        "version": __version__,
    }
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

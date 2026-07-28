"""Argv-only CLI entry for NeuroStudio.

Invoked as: python -m neurostudio <command> [args...]

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .ipc import run_ipc_loop
from .templates import catalog as template_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neurostudio",
        description="NeuroStudio model training worker",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ping = subparsers.add_parser("ping", help="Health check")
    ping.set_defaults(handler=cmd_ping)

    catalog_cmd = subparsers.add_parser(
        "catalog",
        help="Print the model template catalog (ids + param schemas)",
    )
    catalog_cmd.set_defaults(handler=cmd_catalog)

    ipc = subparsers.add_parser(
        "ipc",
        help="JSON-lines IPC server on stdin/stdout",
    )
    ipc.set_defaults(handler=cmd_ipc)

    return parser


def cmd_ping(_args: argparse.Namespace) -> int:
    json.dump(
        {"ok": True, "worker": "neurostudio", "version": __version__},
        sys.stdout,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


def cmd_catalog(_args: argparse.Namespace) -> int:
    json.dump(
        {"ok": True, "result": {"templates": template_catalog()}},
        sys.stdout,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


def cmd_ipc(_args: argparse.Namespace) -> int:
    return run_ipc_loop()


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

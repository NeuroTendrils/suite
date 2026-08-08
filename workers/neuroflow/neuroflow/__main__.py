"""CLI entry for NeuroFlow.

Invoked as: python -m neuroflow <command> [args...]

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .fingerprint import FingerprintError, fingerprint_file
from .run import RunError, run_plan
from .steps import catalog as step_catalog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neuroflow",
        description="NeuroFlow EEG preprocessing worker",
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

    fingerprint = subparsers.add_parser(
        "fingerprint",
        help="Read EEG file metadata (channels, sfreq, duration); no sample dump",
    )
    fingerprint.add_argument(
        "--path",
        required=True,
        help="Path to a local EEG recording (e.g. .fif, .edf, .bdf)",
    )
    fingerprint.set_defaults(handler=cmd_fingerprint)

    catalog_cmd = subparsers.add_parser(
        "catalog",
        help="Print the preprocessing step catalog (ids + param schemas)",
    )
    catalog_cmd.set_defaults(handler=cmd_catalog)

    run_cmd = subparsers.add_parser(
        "run",
        help="Execute a plan JSON against a recording and write cleaned output",
    )
    run_cmd.add_argument("--input", required=True, help="Path to input EEG recording")
    run_cmd.add_argument("--output", required=True, help="Path for cleaned output (.fif)")
    run_cmd.add_argument(
        "--plan",
        required=True,
        help="Path to a NeuroFlow plan JSON file",
    )
    run_cmd.set_defaults(handler=cmd_run)

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


def cmd_fingerprint(args: argparse.Namespace) -> int:
    try:
        payload = fingerprint_file(args.path)
    except FingerprintError as exc:
        json.dump(
            {"ok": False, "error": {"code": exc.code, "message": exc.message}},
            sys.stdout,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 1
    json.dump({"ok": True, "result": payload}, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


def cmd_catalog(_args: argparse.Namespace) -> int:
    payload = {"ok": True, "result": {"steps": step_catalog()}}
    json.dump(payload, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        with open(args.plan, encoding="utf-8") as handle:
            plan = json.load(handle)
        if not isinstance(plan, dict):
            raise RunError("invalid_args", "plan file must contain a JSON object")
        payload = run_plan(args.input, args.output, plan)
    except RunError as exc:
        json.dump(
            {"ok": False, "error": {"code": exc.code, "message": exc.message}},
            sys.stdout,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 1
    except OSError as exc:
        json.dump(
            {
                "ok": False,
                "error": {"code": "read_failed", "message": f"could not read plan: {exc}"},
            },
            sys.stdout,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 1
    except json.JSONDecodeError as exc:
        json.dump(
            {
                "ok": False,
                "error": {"code": "invalid_args", "message": f"plan is not valid JSON: {exc.msg}"},
            },
            sys.stdout,
            separators=(",", ":"),
        )
        sys.stdout.write("\n")
        sys.stdout.flush()
        return 1

    json.dump({"ok": True, "result": payload}, sys.stdout, separators=(",", ":"))
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

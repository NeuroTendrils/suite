from __future__ import annotations

import argparse
import os
import sys

from suite_backend.ipc.server import serve_ipc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="suite-backend")
    parser.add_argument(
        "--ipc",
        required=True,
        help="Path to Unix domain socket (or Windows named pipe path)",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="Root directory for local Study workspaces",
    )
    args = parser.parse_args(argv)
    # New EEG, models and logs are readable only by the current OS account.
    os.umask(0o077)
    serve_ipc(ipc_path=args.ipc, workspace_root=args.workspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

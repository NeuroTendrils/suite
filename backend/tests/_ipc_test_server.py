"""Backend entry point for IPC regression tests (never shipped or allowlisted in Rust).

Registers a few test-only commands with controlled delays and failure modes on top of
the real command registry, then runs the real ``serve_ipc`` loop.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from pydantic import BaseModel

from suite_backend.app_context import AppContext
from suite_backend.ipc.registry import REGISTRY
from suite_backend.ipc.server import serve_ipc


class SlowWriteParams(BaseModel):
    seconds: float
    name: str
    content: str = "result"


class EmptyParams(BaseModel):
    pass


@REGISTRY.register("test.slow_write", SlowWriteParams)
def slow_write(params: SlowWriteParams, ctx: AppContext) -> dict:
    """Simulate a long scientific operation that persists its output before replying."""
    time.sleep(params.seconds)
    out = ctx.workspace.root / "test_outputs" / params.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(params.content, encoding="utf-8")
    return {"path": str(out)}


@REGISTRY.register("test.raise", EmptyParams)
def raise_error(_params: EmptyParams, _ctx: AppContext) -> dict:
    raise RuntimeError("deliberate handler failure")


@REGISTRY.register("test.unserializable", EmptyParams)
def unserializable(_params: EmptyParams, _ctx: AppContext) -> dict:
    return {"value": object()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ipc", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    Path(args.workspace).mkdir(parents=True, exist_ok=True)
    serve_ipc(ipc_path=args.ipc, workspace_root=args.workspace)


if __name__ == "__main__":
    main()

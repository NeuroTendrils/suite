from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

from suite_backend.app_context import AppContext
from suite_backend.ipc import handlers  # noqa: F401 — register commands
from suite_backend.ipc.protocol import RpcRequest
from suite_backend.ipc.registry import REGISTRY


def serve_ipc(ipc_path: str, workspace_root: str) -> None:
    """Serve allowlisted JSON-RPC lines over a Unix domain socket."""
    path = Path(ipc_path)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)

    ctx = AppContext(workspace_root)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chmod(path, 0o600)
    server.listen(8)
    print(json.dumps({"event": "ready", "ipc": str(path), "commands": REGISTRY.allowlist()}), flush=True)

    try:
        while True:
            conn, _ = server.accept()
            with conn:
                _handle_connection(conn, ctx)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
        if path.exists():
            path.unlink()


def _handle_connection(conn: socket.socket, ctx: AppContext) -> None:
    buffer = b""
    while True:
        chunk = conn.recv(65536)
        if not chunk:
            break
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                request = RpcRequest.model_validate_json(line)
            except Exception as exc:  # noqa: BLE001
                payload = {
                    "id": "unknown",
                    "ok": False,
                    "error": f"invalid request: {exc}",
                }
                conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                continue
            response = REGISTRY.dispatch(request, ctx)
            conn.sendall((response.model_dump_json() + "\n").encode("utf-8"))


def main_stdio_debug() -> None:
    """Optional stdio mode for tests (still no TCP)."""
    ctx = AppContext(sys.argv[1] if len(sys.argv) > 1 else "./workspace")
    for line in sys.stdin:
        request = RpcRequest.model_validate_json(line)
        print(REGISTRY.dispatch(request, ctx).model_dump_json(), flush=True)

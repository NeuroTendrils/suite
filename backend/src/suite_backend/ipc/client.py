from __future__ import annotations

import json
import socket
from typing import Any
from uuid import uuid4

from suite_backend.ipc.protocol import RpcResponse


class IpcClient:
    def __init__(self, ipc_path: str) -> None:
        self.ipc_path = ipc_path

    def call(self, command: str, params: dict[str, Any] | None = None) -> RpcResponse:
        request = {
            "id": uuid4().hex,
            "command": command,
            "params": params or {},
        }
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(self.ipc_path)
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
            data = b""
            while b"\n" not in data:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        line = data.split(b"\n", 1)[0]
        return RpcResponse.model_validate_json(line)

"""JSON-lines IPC loop for NeuroStudio.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from . import __version__
from .templates import catalog as template_catalog

PROTOCOL_VERSION = 1


def _write(message: Mapping[str, Any]) -> None:
    sys.stdout.write(json.dumps(dict(message), separators=(",", ":"), ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _success(request_id: str, result: Mapping[str, Any] | None = None) -> None:
    _write(
        {
            "v": PROTOCOL_VERSION,
            "id": request_id,
            "ok": True,
            "result": dict(result or {}),
        }
    )


def _error(
    request_id: str | None,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = dict(details)
    _write(
        {
            "v": PROTOCOL_VERSION,
            "id": request_id or "",
            "ok": False,
            "error": error,
        }
    )


def _handle(request_id: str, cmd: str, args: Mapping[str, Any]) -> None:
    if cmd == "ping":
        _success(
            request_id,
            {
                "pong": True,
                "worker": "neurostudio",
                "version": __version__,
            },
        )
        return

    if cmd == "catalog":
        _success(request_id, {"templates": template_catalog()})
        return

    _error(request_id, "unknown_command", f"unknown command: {cmd}")


def run_ipc_loop() -> int:
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _error(None, "invalid_json", f"malformed JSON: {exc.msg}")
            continue
        if not isinstance(message, dict):
            _error(None, "invalid_request", "message must be a JSON object")
            continue
        version = message.get("v", PROTOCOL_VERSION)
        if version != PROTOCOL_VERSION:
            _error(
                str(message.get("id") or ""),
                "unsupported_version",
                f"unsupported protocol version {version}; expected {PROTOCOL_VERSION}",
            )
            continue
        request_id = message.get("id")
        cmd = message.get("cmd")
        args = message.get("args", {})
        if not isinstance(request_id, str) or not request_id:
            _error(None, "invalid_request", "id must be a non-empty string")
            continue
        if not isinstance(cmd, str) or not cmd:
            _error(request_id, "invalid_request", "cmd must be a non-empty string")
            continue
        if args is None:
            args = {}
        if not isinstance(args, dict):
            _error(request_id, "invalid_request", "args must be an object")
            continue
        _handle(request_id, cmd, args)
    return 0

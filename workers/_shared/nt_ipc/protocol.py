"""JSON-lines request/response/event envelopes for worker IPC.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import json
from typing import Any, Mapping, TextIO

PROTOCOL_VERSION = 1


class ProtocolError(ValueError):
    """Raised when a message is not a valid IPC envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def encode_request(
    request_id: str,
    cmd: str,
    args: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not request_id:
        raise ProtocolError("invalid_request", "request id is required")
    if not cmd:
        raise ProtocolError("invalid_request", "cmd is required")
    return {
        "v": PROTOCOL_VERSION,
        "id": request_id,
        "cmd": cmd,
        "args": dict(args or {}),
    }


def encode_success(request_id: str, result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "id": request_id,
        "ok": True,
        "result": dict(result or {}),
    }


def encode_error(
    request_id: str | None,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "v": PROTOCOL_VERSION,
        "id": request_id or "",
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        payload["error"]["details"] = dict(details)
    return payload


def encode_event(
    request_id: str,
    name: str,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "id": request_id,
        "type": "event",
        "name": name,
        "data": dict(data or {}),
    }


def parse_message(line: str) -> dict[str, Any]:
    text = line.strip()
    if not text:
        raise ProtocolError("invalid_request", "empty message")

    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("invalid_json", f"malformed JSON: {exc.msg}") from exc

    if not isinstance(message, dict):
        raise ProtocolError("invalid_request", "message must be a JSON object")

    version = message.get("v", PROTOCOL_VERSION)
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            "unsupported_version",
            f"unsupported protocol version {version}; expected {PROTOCOL_VERSION}",
        )

    if "cmd" in message:
        _require_str(message, "id")
        _require_str(message, "cmd")
        args = message.get("args", {})
        if args is None:
            message["args"] = {}
        elif not isinstance(args, dict):
            raise ProtocolError("invalid_request", "args must be an object")
        return message

    if message.get("type") == "event":
        _require_str(message, "id")
        _require_str(message, "name")
        data = message.get("data", {})
        if data is None:
            message["data"] = {}
        elif not isinstance(data, dict):
            raise ProtocolError("invalid_event", "data must be an object")
        return message

    if "ok" in message:
        _require_str(message, "id", allow_empty=True)
        ok = message["ok"]
        if not isinstance(ok, bool):
            raise ProtocolError("invalid_response", "ok must be a boolean")
        if ok:
            result = message.get("result", {})
            if result is None:
                message["result"] = {}
            elif not isinstance(result, dict):
                raise ProtocolError("invalid_response", "result must be an object")
        else:
            error = message.get("error")
            if not isinstance(error, dict):
                raise ProtocolError("invalid_response", "error must be an object")
            if not isinstance(error.get("code"), str) or not error["code"]:
                raise ProtocolError("invalid_response", "error.code is required")
            if not isinstance(error.get("message"), str):
                raise ProtocolError("invalid_response", "error.message is required")
        return message

    raise ProtocolError("invalid_request", "unrecognized message shape")


def read_message(stream: TextIO) -> dict[str, Any] | None:
    """Read one JSON-lines message. Returns None on EOF."""
    line = stream.readline()
    if line == "":
        return None
    return parse_message(line)


def write_message(stream: TextIO, message: Mapping[str, Any]) -> None:
    stream.write(json.dumps(dict(message), separators=(",", ":"), ensure_ascii=False))
    stream.write("\n")
    stream.flush()


def _require_str(message: Mapping[str, Any], key: str, *, allow_empty: bool = False) -> None:
    value = message.get(key)
    if not isinstance(value, str):
        raise ProtocolError("invalid_request", f"{key} must be a string")
    if not allow_empty and not value:
        raise ProtocolError("invalid_request", f"{key} must be non-empty")

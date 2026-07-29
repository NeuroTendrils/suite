"""JSON-lines IPC loop for NeuroStudio.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import json
import sys
from typing import Any, Mapping

from . import __version__
from .devices import list_devices
from .export import ExportError, export_model, list_formats
from .templates import catalog as template_catalog
from .train import TrainError, train

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


def _event(request_id: str, name: str, data: Mapping[str, Any] | None = None) -> None:
    _write(
        {
            "v": PROTOCOL_VERSION,
            "id": request_id,
            "type": "event",
            "name": name,
            "data": dict(data or {}),
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

    if cmd == "devices":
        _success(request_id, {"devices": list_devices()})
        return

    if cmd == "formats":
        _success(request_id, {"formats": list_formats()})
        return

    if cmd == "export":
        checkpoint_path = args.get("checkpoint_path")
        output_dir = args.get("output_dir")
        fmt = args.get("format") or "pt"
        train_meta_path = args.get("train_meta_path")
        if not isinstance(checkpoint_path, str) or not checkpoint_path.strip():
            _error(request_id, "invalid_args", "export requires string args.checkpoint_path")
            return
        if not isinstance(output_dir, str) or not output_dir.strip():
            _error(request_id, "invalid_args", "export requires string args.output_dir")
            return
        if not isinstance(fmt, str) or not fmt.strip():
            _error(request_id, "invalid_args", "export args.format must be a string")
            return
        if train_meta_path is not None and not isinstance(train_meta_path, str):
            _error(request_id, "invalid_args", "export args.train_meta_path must be a string")
            return

        def on_progress(data: Mapping[str, Any]) -> None:
            _event(request_id, "export", data)
            message = str(data.get("message") or "")
            if message:
                sys.stderr.write(message + "\n")
                sys.stderr.flush()

        try:
            _success(
                request_id,
                export_model(
                    checkpoint_path=checkpoint_path,
                    output_dir=output_dir,
                    format=fmt,
                    train_meta_path=train_meta_path,
                    on_progress=on_progress,
                ),
            )
        except ExportError as exc:
            _error(request_id, exc.code, exc.message)
        return

    if cmd == "train":
        input_path = args.get("input_path")
        output_dir = args.get("output_dir")
        template_id = args.get("template_id")
        config = args.get("config") or {}
        device = args.get("device") or "cpu"
        if not isinstance(input_path, str) or not input_path.strip():
            _error(request_id, "invalid_args", "train requires string args.input_path")
            return
        if not isinstance(output_dir, str) or not output_dir.strip():
            _error(request_id, "invalid_args", "train requires string args.output_dir")
            return
        if not isinstance(template_id, str) or not template_id.strip():
            _error(request_id, "invalid_args", "train requires string args.template_id")
            return
        if not isinstance(config, dict):
            _error(request_id, "invalid_args", "train args.config must be an object")
            return
        if not isinstance(device, str):
            _error(request_id, "invalid_args", "train args.device must be a string")
            return

        def on_progress(data: Mapping[str, Any]) -> None:
            _event(request_id, "metrics", data)
            message = str(data.get("message") or "")
            if message:
                sys.stderr.write(message + "\n")
                sys.stderr.flush()

        try:
            _success(
                request_id,
                train(
                    input_path=input_path,
                    output_dir=output_dir,
                    template_id=template_id,
                    config=config,
                    device=device,
                    on_progress=on_progress,
                ),
            )
        except TrainError as exc:
            _error(request_id, exc.code, exc.message)
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

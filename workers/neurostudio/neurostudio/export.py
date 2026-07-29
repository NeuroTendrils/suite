"""Export trained NeuroStudio checkpoints to portable formats.

Formats: pt, torchscript, onnx, safetensors.
Writes the artifact plus a model.json sidecar into the caller-provided
output directory (typically project models/<name>/).

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .templates import find_template
from .train import _build_model

ProgressCb = Callable[[dict[str, Any]], None]

FORMATS: dict[str, dict[str, str]] = {
    "pt": {
        "label": "PyTorch (.pt)",
        "filename": "model.pt",
        "description": "Full portable package (weights + rebuild metadata).",
    },
    "torchscript": {
        "label": "TorchScript",
        "filename": "model.ts.pt",
        "description": "Traced TorchScript module for C++ / LibTorch.",
    },
    "onnx": {
        "label": "ONNX",
        "filename": "model.onnx",
        "description": "ONNX graph for broad runtime interoperability.",
    },
    "safetensors": {
        "label": "SafeTensors",
        "filename": "model.safetensors",
        "description": "Weights-only SafeTensors tensor store.",
    },
}


class ExportError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def list_formats() -> list[dict[str, str]]:
    return [
        {"id": key, "label": meta["label"], "filename": meta["filename"], "description": meta["description"]}
        for key, meta in FORMATS.items()
    ]


def export_model(
    *,
    checkpoint_path: str | Path,
    output_dir: str | Path,
    format: str = "pt",
    train_meta_path: str | Path | None = None,
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Export a Studio checkpoint into *output_dir*."""
    ckpt_path = Path(checkpoint_path).expanduser()
    out_dir = Path(output_dir).expanduser()
    fmt = (format or "pt").strip().lower()

    if not str(checkpoint_path).strip():
        raise ExportError("invalid_args", "checkpoint_path is required")
    if not str(output_dir).strip():
        raise ExportError("invalid_args", "output_dir is required")
    if not ckpt_path.is_file():
        raise ExportError("file_not_found", f"checkpoint not found: {ckpt_path}")
    if fmt not in FORMATS:
        raise ExportError(
            "invalid_args",
            f"unknown format {format!r}; expected one of {', '.join(FORMATS)}",
        )

    try:
        import torch
    except ImportError as exc:
        raise ExportError(
            "dependency_missing",
            "torch is required for export; install neurostudio requirements",
        ) from exc

    def progress(payload: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(payload)

    progress({"stage": "load", "message": "Loading checkpoint…"})
    try:
        blob = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    except TypeError:
        blob = torch.load(ckpt_path, map_location="cpu")
    if not isinstance(blob, dict) or "model_state" not in blob:
        raise ExportError("invalid_checkpoint", "checkpoint is missing model_state")

    template_id = str(blob.get("template_id") or "")
    config = dict(blob.get("config") or {})
    n_channels = int(blob.get("n_channels") or 0)
    n_times = int(blob.get("n_times") or 0)
    n_classes = int(blob.get("n_classes") or 0)
    class_names = list(blob.get("class_names") or [])
    model_family = str(blob.get("model_family") or "")

    if n_channels < 1 or n_times < 1 or n_classes < 2:
        raise ExportError(
            "invalid_checkpoint",
            "checkpoint is missing n_channels / n_times / n_classes",
        )

    template = find_template(template_id) or {
        "id": template_id,
        "title": template_id or "exported model",
        "task": "",
        "model_family": model_family,
    }

    progress({"stage": "build", "message": f"Rebuilding model for {fmt}…"})
    model = _build_model(
        template=template,
        n_channels=n_channels,
        n_times=n_times,
        n_classes=n_classes,
        config=config,
    )
    model.load_state_dict(blob["model_state"])
    model.eval()

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_name = FORMATS[fmt]["filename"]
    artifact_path = out_dir / artifact_name
    meta_path = out_dir / "model.json"

    progress({"stage": "export", "message": f"Writing {artifact_name}…"})
    if fmt == "pt":
        torch.save(
            {
                "model_state": model.state_dict(),
                "template_id": template_id,
                "config": config,
                "n_channels": n_channels,
                "n_times": n_times,
                "n_classes": n_classes,
                "class_names": class_names,
                "model_family": model_family or template.get("model_family"),
                "format": "pt",
            },
            artifact_path,
        )
    elif fmt == "torchscript":
        example = torch.zeros(1, 1, n_channels, n_times)
        traced = torch.jit.trace(model, example)
        traced.save(str(artifact_path))
    elif fmt == "onnx":
        _export_onnx(model, artifact_path, n_channels=n_channels, n_times=n_times)
    elif fmt == "safetensors":
        try:
            from safetensors.torch import save_file
        except ImportError as exc:
            raise ExportError(
                "dependency_missing",
                "safetensors is required for this format; install neurostudio requirements",
            ) from exc
        save_file(model.state_dict(), str(artifact_path))

    train_meta: dict[str, Any] = {}
    if train_meta_path:
        tm = Path(train_meta_path).expanduser()
        if tm.is_file():
            try:
                train_meta = json.loads(tm.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                train_meta = {}

    # Also try sibling train.json next to the checkpoint.
    if not train_meta:
        sibling = ckpt_path.parent / "train.json"
        if sibling.is_file():
            try:
                train_meta = json.loads(sibling.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                train_meta = {}

    metrics = {}
    if isinstance(train_meta.get("metrics"), dict):
        metrics = dict(train_meta["metrics"])

    sidecar = {
        "kind": "neurostudio_model",
        "version": 1,
        "title": str(template.get("title") or template_id or artifact_name),
        "template_id": template_id,
        "template_title": template.get("title"),
        "task": template.get("task"),
        "model_family": model_family or template.get("model_family"),
        "format": fmt,
        "format_label": FORMATS[fmt]["label"],
        "artifact": artifact_name,
        "artifact_path": str(artifact_path.resolve()),
        "checkpoint_path": str(ckpt_path.resolve()),
        "output_dir": str(out_dir.resolve()),
        "n_channels": n_channels,
        "n_times": n_times,
        "n_classes": n_classes,
        "class_names": class_names,
        "config": config,
        "metrics": metrics,
        "data_mode": train_meta.get("data_mode"),
        "device": train_meta.get("device"),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "torch_version": getattr(torch, "__version__", "unknown"),
        "visibility": "local",
        "publish_status": "unpublished",
    }
    meta_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    # Keep a small copy of train metrics alongside for Hub convenience.
    if metrics:
        (out_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )

    # For .pt format, optionally mirror original checkpoint name for familiarity.
    if fmt == "pt" and ckpt_path.name != artifact_name:
        try:
            shutil.copy2(artifact_path, out_dir / "checkpoint.pt")
        except OSError:
            pass

    progress(
        {
            "stage": "done",
            "message": f"Exported {fmt} → {artifact_name}",
            "format": fmt,
            "artifact_path": str(artifact_path),
        }
    )

    return {
        "format": fmt,
        "format_label": FORMATS[fmt]["label"],
        "output_dir": str(out_dir.resolve()),
        "artifact_path": str(artifact_path.resolve()),
        "metadata_path": str(meta_path.resolve()),
        "model": sidecar,
    }


def _export_onnx(
    model: Any, path: Path, *, n_channels: int, n_times: int
) -> None:
    import torch

    example = torch.zeros(1, 1, n_channels, n_times)
    kwargs = dict(
        input_names=["eeg"],
        output_names=["logits"],
        dynamic_axes={"eeg": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )
    # Torch 2.5+ defaults toward the dynamo exporter (needs onnxscript).
    # Prefer the classic exporter when available for fewer host deps.
    try:
        torch.onnx.export(
            model, example, str(path), dynamo=False, **kwargs
        )
        return
    except TypeError:
        pass
    except Exception as exc:  # noqa: BLE001
        last = exc
    else:
        last = None

    try:
        torch.onnx.export(model, example, str(path), **kwargs)
    except Exception as exc:  # noqa: BLE001
        detail = exc if last is None else f"{last}; retry: {exc}"
        raise ExportError("export_failed", f"ONNX export failed: {detail}") from exc
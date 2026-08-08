"""Run inference with a NeuroStudio checkpoint on epochs or a dataset.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .devices import resolve_device
from .templates import find_template
from .train import TrainError, _build_model, _prepare_arrays

ProgressCb = Callable[[dict[str, Any]], None]


class PredictError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def predict(
    *,
    checkpoint_path: str | Path,
    input_path: str | Path = "",
    dataset_path: str | Path | None = None,
    output_dir: str | Path,
    device: str = "cpu",
    on_progress: ProgressCb | None = None,
) -> dict[str, Any]:
    """Load checkpoint, run forward pass, write predictions.json under output_dir."""
    ckpt_path = Path(checkpoint_path).expanduser()
    out_dir = Path(output_dir).expanduser()
    in_path = Path(input_path).expanduser() if input_path else Path()
    ds_path = Path(dataset_path).expanduser() if dataset_path else None

    if not ckpt_path.is_file():
        raise PredictError("file_not_found", f"checkpoint not found: {ckpt_path}")
    if ds_path is None and not in_path.is_file():
        raise PredictError("invalid_args", "input_path or dataset_path is required")
    if not str(output_dir).strip():
        raise PredictError("invalid_args", "output_dir is required")

    try:
        import torch
    except ImportError as exc:
        raise PredictError(
            "dependency_missing",
            "torch is required for predict; install neurostudio requirements",
        ) from exc

    def progress(payload: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(payload)

    progress({"stage": "load", "message": "Loading checkpoint…"})
    try:
        blob = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    except TypeError:
        blob = torch.load(ckpt_path, map_location="cpu")
    except Exception as exc:  # noqa: BLE001
        raise PredictError("read_failed", f"could not load checkpoint: {exc}") from exc

    if not isinstance(blob, dict):
        raise PredictError("invalid_args", "checkpoint is not a NeuroStudio package")

    template_id = str(blob.get("template_id") or "")
    template = find_template(template_id)
    if template is None:
        raise PredictError("invalid_args", f"unknown template in checkpoint: {template_id}")

    class_names = [str(c) for c in (blob.get("class_names") or [])]
    n_channels = int(blob.get("n_channels") or 0)
    n_times = int(blob.get("n_times") or 0)
    n_classes = int(blob.get("n_classes") or len(class_names) or 0)
    config = dict(blob.get("config") or {})
    if n_channels < 1 or n_times < 1 or n_classes < 2:
        raise PredictError("invalid_args", "checkpoint missing model geometry")

    progress({"stage": "data", "message": "Loading data…"})
    if ds_path is not None:
        from .dataset_load import prepare_from_dataset

        x, y, data_mode, data_meta, _split = prepare_from_dataset(
            ds_path, seed=int(config.get("seed", 42)), prepare_file=_prepare_arrays
        )
    else:
        x, y, data_mode, data_meta = _prepare_arrays(in_path, seed=int(config.get("seed", 42)))

    # Match train geometry (cap / pad times).
    if x.shape[3] != n_times:
        if x.shape[3] > n_times:
            x = x[:, :, :, :n_times]
        else:
            pad = n_times - x.shape[3]
            x = np.pad(x, ((0, 0), (0, 0), (0, 0), (0, pad)))
    if x.shape[2] != n_channels:
        raise PredictError(
            "invalid_data",
            f"channel count mismatch: data has {x.shape[2]}, model expects {n_channels}",
        )

    try:
        device_name = resolve_device(device)
    except ValueError as exc:
        raise PredictError("invalid_args", str(exc)) from exc
    torch_device = torch.device(device_name)

    model = _build_model(
        template=template,
        n_channels=n_channels,
        n_times=n_times,
        n_classes=n_classes,
        config=config,
    )
    state = blob.get("model_state") or blob.get("state_dict")
    if state is None:
        raise PredictError("invalid_args", "checkpoint has no model weights")
    model.load_state_dict(state)
    model.to(torch_device)
    model.eval()

    progress({"stage": "infer", "message": f"Running inference on {len(x)} trials…"})
    preds: list[int] = []
    probs: list[list[float]] = []
    batch = 64
    with torch.no_grad():
        for start in range(0, len(x), batch):
            chunk = torch.tensor(x[start : start + batch], dtype=torch.float32, device=torch_device)
            logits = model(chunk)
            prob = torch.softmax(logits, dim=1).cpu().numpy()
            pred = np.argmax(prob, axis=1)
            preds.extend(int(p) for p in pred.tolist())
            probs.extend([[float(v) for v in row] for row in prob.tolist()])

    labels = [class_names[i] if i < len(class_names) else str(i) for i in preds]
    has_truth = y is not None and len(y) == len(preds) and data_mode != "synthetic_demo"
    metrics: dict[str, Any] = {}
    if has_truth:
        y_arr = np.asarray(y, dtype=int)
        pred_arr = np.asarray(preds, dtype=int)
        acc = float(np.mean(pred_arr == y_arr)) if len(y_arr) else 0.0
        metrics = {
            "accuracy": acc,
            "n_trials": int(len(y_arr)),
            "n_correct": int(np.sum(pred_arr == y_arr)),
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "v": 1,
        "kind": "neurostudio_inference",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checkpoint_path": str(ckpt_path.resolve()),
        "template_id": template_id,
        "class_names": class_names,
        "data_mode": data_mode,
        "input_path": str(in_path) if in_path else "",
        "dataset_path": str(ds_path) if ds_path else "",
        "predictions": labels,
        "prediction_indices": preds,
        "probabilities": probs,
        "metrics": metrics,
        "meta": {k: data_meta.get(k) for k in ("class_names", "n_members", "split_mode") if k in data_meta},
    }
    out_file = out_dir / "predictions.json"
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    progress({"stage": "done", "message": f"Wrote {out_file.name}"})
    return {
        "output_path": str(out_file.resolve()),
        "n_trials": len(preds),
        "class_names": class_names,
        "metrics": metrics,
        "template_id": template_id,
    }

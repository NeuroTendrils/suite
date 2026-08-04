"""Local model training for NeuroStudio templates.

Emits JSON-lines progress events via an optional callback. Saves checkpoints
and metrics under the caller-provided output directory.

Label sources (in order):
  1. Epoched FIF with per-trial event codes (data_mode=labeled_epochs)
  2. Continuous FIF with annotations or stim events, epoched on the fly
     (data_mode=labeled_raw)
  3. synthetic_demo only when no usable labels are found

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .devices import resolve_device
from .templates import default_config, find_template, validate_config

# Cap trials so interactive Studio trains stay responsive.
_MAX_TRIALS = 512
_MAX_TIMES = 256


class TrainError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


ProgressCb = Callable[[dict[str, Any]], None]


def train(
    *,
    input_path: str | Path = "",
    output_dir: str | Path,
    template_id: str,
    config: dict[str, Any] | None = None,
    device: str = "cpu",
    on_progress: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
    allow_synthetic: bool = False,
    dataset_path: str | Path | None = None,
) -> dict[str, Any]:
    """Train a template and write artifacts into *output_dir*."""
    in_path = Path(input_path).expanduser() if input_path else Path()
    ds_path = Path(dataset_path).expanduser() if dataset_path else None
    out_dir = Path(output_dir).expanduser()

    if ds_path is None and not str(input_path).strip():
        raise TrainError("invalid_args", "input_path or dataset_path is required")
    if not str(output_dir).strip():
        raise TrainError("invalid_args", "output_dir is required")
    if ds_path is not None:
        from .dataset_load import is_manifest_path

        if not is_manifest_path(ds_path):
            raise TrainError("file_not_found", f"dataset manifest not found: {ds_path}")
    elif not in_path.is_file():
        raise TrainError("file_not_found", f"input file not found: {in_path}")
    if out_dir.exists() and out_dir.is_symlink():
        raise TrainError("invalid_args", "output_dir must not be a symlink")

    template = find_template(template_id)
    if template is None:
        raise TrainError("invalid_args", f"unknown template: {template_id}")

    merged = default_config(template_id)
    if config:
        merged.update(config)
    error = validate_config(template_id, merged)
    if error:
        raise TrainError("invalid_params", error)

    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError as exc:
        raise TrainError(
            "dependency_missing",
            "torch is required for train; install neurostudio requirements",
        ) from exc

    try:
        device_name = resolve_device(device)
    except ValueError as exc:
        raise TrainError("invalid_args", str(exc)) from exc

    torch_device = torch.device(device_name)
    seed = int(merged.get("seed", 42))
    _seed_everything(seed)

    def progress(payload: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(payload)

    progress({"stage": "load", "message": "Preparing training data…"})
    roles = None
    if ds_path is not None:
        from .dataset_load import prepare_from_dataset, split_indices

        x, y, data_mode, data_meta, roles = prepare_from_dataset(
            ds_path, seed=seed, prepare_file=_prepare_arrays
        )
    else:
        x, y, data_mode, data_meta = _prepare_arrays(in_path, seed=seed)

    if data_mode == "synthetic_demo" and not allow_synthetic:
        note = data_meta.get("note") or data_meta.get("epochs_label_warning") or ""
        raise TrainError(
            "no_labels",
            "No usable trial labels found. "
            "Use a labeled dataset (embedded events, filename classes, or data+label .mat), "
            f"not unlabeled windows. {note}".strip(),
        )

    if x.shape[0] < 4:
        raise TrainError(
            "invalid_data",
            "Need at least 4 labeled trials across the dataset.",
        )

    n_classes = int(len(np.unique(y)))
    if n_classes < 2:
        raise TrainError(
            "invalid_data",
            "Need at least 2 classes to train; check event labels or filename class tags.",
        )
    n_channels = int(x.shape[2])
    n_times = int(x.shape[3])

    if ds_path is not None:
        from .dataset_load import split_indices

        train_idx, val_idx = split_indices(
            y,
            seed=seed,
            split_mode=str(data_meta.get("split_mode") or "stratified"),
            val_fraction=float(data_meta.get("val_fraction") or 0.2),
            roles=roles,
            stratified_split=_stratified_split,
        )
    else:
        train_idx, val_idx = _stratified_split(y, seed=seed)

    x_train = torch.tensor(x[train_idx], dtype=torch.float32)
    y_train = torch.tensor(y[train_idx], dtype=torch.long)
    x_val = torch.tensor(x[val_idx], dtype=torch.float32)
    y_val = torch.tensor(y[val_idx], dtype=torch.long)

    batch_size = int(merged.get("batch_size", 64))
    epochs = int(merged.get("epochs", 40))
    lr = float(merged.get("lr", 1e-3))
    weight_decay = float(merged.get("weight_decay", 0.0))

    train_loader = DataLoader(
        TensorDataset(x_train, y_train),
        batch_size=min(batch_size, len(y_train)),
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(x_val, y_val),
        batch_size=min(batch_size, len(y_val)),
        shuffle=False,
    )

    model = _build_model(
        template=template,
        n_channels=n_channels,
        n_times=n_times,
        n_classes=n_classes,
        config=merged,
    ).to(torch_device)

    optimizer_name = str(merged.get("optimizer", "adam")).lower()
    if optimizer_name == "adamw":
        optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    elif optimizer_name == "sgd":
        optimizer = torch.optim.SGD(
            model.parameters(), lr=lr, momentum=0.9, weight_decay=weight_decay
        )
    else:
        optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)

    criterion = nn.CrossEntropyLoss()
    history: list[dict[str, Any]] = []

    progress(
        {
            "stage": "train",
            "message": f"Training on {device_name} ({data_mode})…",
            "device": device_name,
            "data_mode": data_mode,
            "n_train": int(len(y_train)),
            "n_val": int(len(y_val)),
            "n_classes": n_classes,
            "class_names": data_meta.get("class_names", []),
        }
    )

    for epoch in range(1, epochs + 1):
        if should_cancel and should_cancel():
            raise TrainError("cancelled", "Training cancelled")
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        for xb, yb in train_loader:
            xb = xb.to(torch_device)
            yb = yb.to(torch_device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item()) * len(yb)
            preds = logits.argmax(dim=1)
            correct += int((preds == yb).sum().item())
            total += len(yb)

        train_loss = running_loss / max(1, total)
        train_acc = correct / max(1, total)
        val_loss, val_acc, _ = _evaluate(model, val_loader, criterion, torch_device)

        row = {
            "epoch": epoch,
            "loss": train_loss,
            "accuracy": train_acc,
            "val_loss": val_loss,
            "val_accuracy": val_acc,
        }
        history.append(row)
        progress(
            {
                "stage": "epoch",
                "message": (
                    f"Epoch {epoch}/{epochs}  "
                    f"loss={train_loss:.4f} acc={train_acc:.3f}  "
                    f"val_loss={val_loss:.4f} val_acc={val_acc:.3f}"
                ),
                **row,
                "total_epochs": epochs,
            }
        )

    progress({"stage": "evaluate", "message": "Computing final metrics…"})
    _, final_acc, logits_np_y = _evaluate(
        model, val_loader, criterion, torch_device, return_preds=True
    )
    y_true, y_pred = logits_np_y
    confusion = _confusion_matrix(y_true, y_pred, n_classes)
    bal_acc = _balanced_accuracy(confusion)

    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / "checkpoint.pt"
    metrics_path = out_dir / "metrics.json"
    train_meta_path = out_dir / "train.json"

    torch.save(
        {
            "model_state": model.state_dict(),
            "template_id": template_id,
            "config": merged,
            "n_channels": n_channels,
            "n_times": n_times,
            "n_classes": n_classes,
            "class_names": data_meta.get("class_names", []),
            "model_family": template.get("model_family"),
        },
        checkpoint_path,
    )

    metrics = {
        "accuracy": float(final_acc),
        "balanced_accuracy": float(bal_acc),
        "confusion": confusion,
        "n_classes": n_classes,
        "class_names": data_meta.get("class_names", []),
        "history": history,
        "primary": template.get("metrics", {}).get("primary", "accuracy"),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    summary = {
        "input_path": str(in_path.resolve()) if in_path and in_path.exists() else "",
        "dataset_path": str(ds_path.resolve()) if ds_path is not None else "",
        "output_dir": str(out_dir.resolve()),
        "checkpoint_path": str(checkpoint_path.resolve()),
        "metrics_path": str(metrics_path.resolve()),
        "train_meta_path": str(train_meta_path.resolve()),
        "template_id": template_id,
        "config": merged,
        "device": device_name,
        "data_mode": data_mode,
        "data": data_meta,
        "metrics": {
            "accuracy": metrics["accuracy"],
            "balanced_accuracy": metrics["balanced_accuracy"],
            "confusion": confusion,
            "n_classes": n_classes,
            "class_names": metrics["class_names"],
            "primary": metrics["primary"],
        },
        "history": history,
        "n_epochs": epochs,
        "torch_version": getattr(torch, "__version__", "unknown"),
    }
    train_meta_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    progress(
        {
            "stage": "done",
            "message": (
                f"Done. val_acc={final_acc:.3f} bal_acc={bal_acc:.3f} "
                f"→ {checkpoint_path.name}"
            ),
            "accuracy": float(final_acc),
            "balanced_accuracy": float(bal_acc),
        }
    )
    return summary


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _prepare_arrays(
    path: Path, *, seed: int, allow_single_class: bool = False
) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any]]:
    """Return X (n, 1, C, T), y, data_mode, meta."""
    meta: dict[str, Any] = {"source": str(path)}

    try:
        import mne
    except ImportError as exc:
        meta["load_warning"] = f"mne missing: {exc}"
        return _synthetic_demo(seed=seed, meta=meta)

    # 1) Epoched FIF with real trial labels
    try:
        epochs = mne.read_epochs(str(path), preload=True, verbose="ERROR")
        packed = _from_epochs(
            epochs, seed=seed, meta=meta, allow_single_class=allow_single_class
        )
        if packed is not None:
            return packed
        meta["epochs_label_warning"] = (
            "Epoched FIF loaded but events did not yield usable classes"
            if allow_single_class
            else "Epoched FIF loaded but events did not yield ≥2 usable classes"
        )
    except Exception as exc:  # noqa: BLE001
        meta["epochs_load_note"] = str(exc)

    # 2) Continuous raw: annotations or stim-channel events → epoch
    try:
        raw = mne.io.read_raw(str(path), preload=True, verbose="ERROR")
        packed = _from_raw_labeled(raw, seed=seed, meta=meta)
        if packed is not None:
            return packed
        meta["raw_label_warning"] = (
            "Continuous FIF has no usable annotations/stim events for labels"
        )
    except Exception as exc:  # noqa: BLE001
        meta["raw_load_note"] = str(exc)
        meta["load_warning"] = str(exc)

    return _synthetic_demo(seed=seed, meta=meta)


def _from_epochs(
    epochs: Any,
    *,
    seed: int,
    meta: dict[str, Any],
    allow_single_class: bool = False,
) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any]] | None:
    """Build arrays from an Epochs object using real event codes."""
    import mne

    if not isinstance(epochs, mne.BaseEpochs):
        return None
    min_trials = 1 if allow_single_class else 4
    if len(epochs) < min_trials:
        return None

    event_id = dict(epochs.event_id or {})
    codes = np.asarray(epochs.events[:, 2], dtype=np.int64)
    y, class_names, code_to_class = _remap_codes(
        codes, event_id, allow_single_class=allow_single_class
    )
    if y is None:
        return None

    picks = mne.pick_types(epochs.info, eeg=True, meg=False, exclude="bads")
    if len(picks) == 0:
        picks = np.arange(min(8, len(epochs.ch_names)))
    data = epochs.get_data(picks=picks, copy=True)
    return _pack_trials(
        data,
        y,
        class_names=class_names,
        code_to_class=code_to_class,
        sfreq=float(epochs.info["sfreq"]),
        seed=seed,
        meta=meta,
        data_mode="labeled_epochs",
        mne_kind="epochs",
        label_source="epochs.events",
    )


def _from_raw_labeled(
    raw: Any, *, seed: int, meta: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any]] | None:
    """Epoch continuous raw around annotations or stim events."""
    import mne

    events: np.ndarray | None = None
    event_id: dict[str, int] = {}
    label_source = ""

    # Prefer annotations (common after set_annotations / BIDS / experiment logs).
    try:
        if raw.annotations is not None and len(raw.annotations) > 0:
            events, event_id = mne.events_from_annotations(
                raw, verbose="ERROR"
            )
            # Drop obvious non-trial markers.
            keep_names = [
                name
                for name in event_id
                if not name.upper().startswith(("BAD", "EDGE", "REJECT"))
            ]
            if keep_names:
                event_id = {k: event_id[k] for k in keep_names}
                keep_codes = set(event_id.values())
                events = events[np.isin(events[:, 2], list(keep_codes))]
                label_source = "annotations"
    except Exception as exc:  # noqa: BLE001
        meta["annotations_note"] = str(exc)

    # Stim / trigger channel fallback.
    if events is None or len(events) == 0 or len(event_id) < 2:
        try:
            stim_events = mne.find_events(raw, verbose="ERROR", shortest_event=1)
            if stim_events is not None and len(stim_events) > 0:
                codes = sorted(int(c) for c in np.unique(stim_events[:, 2]))
                # Need ≥2 distinct non-zero codes.
                codes = [c for c in codes if c != 0]
                if len(codes) >= 2:
                    events = stim_events[np.isin(stim_events[:, 2], codes)]
                    event_id = {f"event_{c}": c for c in codes}
                    label_source = "stim"
        except Exception as exc:  # noqa: BLE001
            meta["stim_note"] = str(exc)

    if events is None or len(events) < 4 or len(event_id) < 2:
        return None

    sfreq = float(raw.info["sfreq"])
    # ~0.5 s windows by default; clamp for very low/high rates.
    tmax = min(1.0, max(0.25, 128.0 / sfreq))
    try:
        epochs = mne.Epochs(
            raw,
            events,
            event_id=event_id,
            tmin=0.0,
            tmax=tmax,
            baseline=None,
            preload=True,
            reject_by_annotation=True,
            verbose="ERROR",
        )
    except Exception as exc:  # noqa: BLE001
        meta["epoching_note"] = str(exc)
        return None

    if len(epochs) < 4:
        return None

    codes = np.asarray(epochs.events[:, 2], dtype=np.int64)
    y, class_names, code_to_class = _remap_codes(codes, event_id)
    if y is None:
        return None

    picks = mne.pick_types(epochs.info, eeg=True, meg=False, exclude="bads")
    if len(picks) == 0:
        picks = np.arange(min(8, len(epochs.ch_names)))
    data = epochs.get_data(picks=picks, copy=True)
    return _pack_trials(
        data,
        y,
        class_names=class_names,
        code_to_class=code_to_class,
        sfreq=sfreq,
        seed=seed,
        meta=meta,
        data_mode="labeled_raw",
        mne_kind="raw",
        label_source=label_source or "events",
    )


def _remap_codes(
    codes: np.ndarray,
    event_id: dict[str, int],
    *,
    allow_single_class: bool = False,
) -> tuple[np.ndarray | None, list[str], dict[str, int]]:
    """Map raw event codes → contiguous 0..C-1 class indices."""
    # Prefer names from event_id; unknowns become event_<code>.
    code_to_name = {int(v): str(k) for k, v in (event_id or {}).items()}
    present = sorted(int(c) for c in np.unique(codes))
    min_classes = 1 if allow_single_class else 2
    if len(present) < min_classes:
        return None, [], {}

    class_names = [code_to_name.get(c, f"event_{c}") for c in present]
    code_to_class = {c: i for i, c in enumerate(present)}
    y = np.asarray([code_to_class[int(c)] for c in codes], dtype=np.int64)
    if len(np.unique(y)) < min_classes:
        return None, [], {}
    return y, class_names, {str(k): int(v) for k, v in code_to_class.items()}


def _pack_trials(
    data: np.ndarray,
    y: np.ndarray,
    *,
    class_names: list[str],
    code_to_class: dict[str, int],
    sfreq: float,
    seed: int,
    meta: dict[str, Any],
    data_mode: str,
    mne_kind: str,
    label_source: str,
) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any]]:
    n_times = int(min(data.shape[2], _MAX_TIMES))
    data = data[:, :, :n_times]

    if data.shape[0] > _MAX_TRIALS:
        rng = np.random.default_rng(seed)
        keep = rng.choice(data.shape[0], size=_MAX_TRIALS, replace=False)
        keep.sort()
        data = data[keep]
        y = y[keep]

    # Drop classes that disappeared after subsampling if that collapses to <2.
    present = sorted(int(c) for c in np.unique(y))
    if len(present) < 2:
        # Should be rare; caller will fall through if we returned None — keep as-is
        # and let train() raise invalid_data.
        pass
    else:
        remap = {old: new for new, old in enumerate(present)}
        y = np.asarray([remap[int(v)] for v in y], dtype=np.int64)
        class_names = [class_names[i] for i in present]

    x = data[:, None, :, :].astype(np.float32)
    meta.update(
        {
            "mne_kind": mne_kind,
            "label_source": label_source,
            "sfreq": sfreq,
            "n_channels": int(x.shape[2]),
            "n_times": int(x.shape[3]),
            "n_samples": int(x.shape[0]),
            "n_classes": int(len(np.unique(y))),
            "class_names": class_names,
            "code_to_class": code_to_class,
        }
    )
    return x, y.astype(np.int64), data_mode, meta


def _stratified_split(y: np.ndarray, *, seed: int, train_frac: float = 0.8) -> tuple[np.ndarray, np.ndarray]:
    """Per-class shuffle split; falls back to a plain shuffle if needed."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y)
    train_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []
    for label in np.unique(y):
        idx = np.flatnonzero(y == label)
        rng.shuffle(idx)
        if len(idx) == 1:
            train_parts.append(idx)
            continue
        split = max(1, int(round(train_frac * len(idx))))
        split = min(split, len(idx) - 1)
        train_parts.append(idx[:split])
        val_parts.append(idx[split:])
    if not train_parts:
        idx = np.arange(len(y))
        rng.shuffle(idx)
        split = max(1, int(train_frac * len(idx)))
        return idx[:split], idx[split:] if split < len(idx) else idx[:1]
    train_idx = np.concatenate(train_parts)
    rng.shuffle(train_idx)
    if val_parts:
        val_idx = np.concatenate(val_parts)
        rng.shuffle(val_idx)
    else:
        val_idx = train_idx[: max(1, len(train_idx) // 5)]
    return train_idx, val_idx


def _synthetic_demo(
    *, seed: int, meta: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any]]:
    """Last-resort pipeline check: invent labels + inject a class cue."""
    n_channels = 8
    n_times = 128
    n_classes = 4
    n_samples = 128
    sfreq = 250.0
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, size=(n_samples, 1, n_channels, n_times)).astype(np.float32)
    y = rng.integers(0, n_classes, size=n_samples)
    for i, label in enumerate(y):
        x[i, 0, label % n_channels, :] += 0.8
    class_names = [f"synth_{i}" for i in range(n_classes)]
    meta.update(
        {
            "mne_kind": meta.get("mne_kind", "synthetic"),
            "label_source": "synthetic",
            "sfreq": sfreq,
            "n_channels": n_channels,
            "n_times": n_times,
            "n_samples": n_samples,
            "n_classes": n_classes,
            "class_names": class_names,
            "note": (
                "No usable trial labels found in the FIF. "
                "Using synthetic_demo (not scientifically meaningful)."
            ),
        }
    )
    return x, y.astype(np.int64), "synthetic_demo", meta


def _build_model(
    *,
    template: dict[str, Any],
    n_channels: int,
    n_times: int,
    n_classes: int,
    config: dict[str, Any],
):
    import torch
    import torch.nn as nn

    family = str(template.get("model_family", "eegnet")).lower()
    drop = float(config.get("drop_prob", 0.25))
    f1 = int(config.get("F1", config.get("n_filters_time", 8)))
    depth = int(config.get("D", config.get("depth_multiplier", 2)))
    k_cfg = int(config.get("kernel_length", config.get("filter_time_length", 0)) or 0)
    k_time = k_cfg if k_cfg >= 8 else max(8, min(32, max(8, n_times // 4)))
    k_time = max(8, min(64, k_time))

    class TinyEEGNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            spatial_out = max(f1, f1 * max(1, depth))
            self.temporal = nn.Sequential(
                nn.Conv2d(1, f1, kernel_size=(1, k_time), padding=(0, k_time // 2)),
                nn.BatchNorm2d(f1),
                nn.ELU(),
                nn.AvgPool2d(kernel_size=(1, 4)),
                nn.Dropout(drop),
            )
            self.spatial = nn.Sequential(
                nn.Conv2d(f1, spatial_out, kernel_size=(n_channels, 1)),
                nn.BatchNorm2d(spatial_out),
                nn.ELU(),
                nn.AdaptiveAvgPool2d((1, 8)),
                nn.Flatten(),
            )
            with torch.no_grad():
                probe = torch.zeros(1, 1, n_channels, n_times)
                n_in = int(self.spatial(self.temporal(probe)).shape[-1])
            self.classifier = nn.Linear(n_in, n_classes)

        def forward(self, x):
            return self.classifier(self.spatial(self.temporal(x)))

    class TinyShallow(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(1, f1, kernel_size=(1, k_time), padding=(0, k_time // 2)),
                nn.Conv2d(f1, f1, kernel_size=(n_channels, 1)),
                nn.BatchNorm2d(f1),
                nn.ELU(),
                nn.AvgPool2d(kernel_size=(1, 8)),
                nn.Dropout(drop),
                nn.Flatten(),
            )
            with torch.no_grad():
                probe = torch.zeros(1, 1, n_channels, n_times)
                n_in = int(self.features(probe).shape[-1])
            self.classifier = nn.Linear(n_in, n_classes)

        def forward(self, x):
            return self.classifier(self.features(x))

    if "shallow" in family:
        return TinyShallow()
    return TinyEEGNet()


def _evaluate(model, loader, criterion, device, return_preds: bool = False):
    import torch

    model.eval()
    loss_sum = 0.0
    correct = 0
    total = 0
    ys: list[int] = []
    preds: list[int] = []
    with torch.no_grad():
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            logits = model(xb)
            loss = criterion(logits, yb)
            loss_sum += float(loss.item()) * len(yb)
            pred = logits.argmax(dim=1)
            correct += int((pred == yb).sum().item())
            total += len(yb)
            if return_preds:
                ys.extend(int(v) for v in yb.cpu().tolist())
                preds.extend(int(v) for v in pred.cpu().tolist())
    avg_loss = loss_sum / max(1, total)
    acc = correct / max(1, total)
    if return_preds:
        return avg_loss, acc, (ys, preds)
    return avg_loss, acc, None


def _confusion_matrix(y_true: list[int], y_pred: list[int], n_classes: int) -> list[list[int]]:
    mat = [[0 for _ in range(n_classes)] for _ in range(n_classes)]
    for t, p in zip(y_true, y_pred, strict=False):
        if 0 <= t < n_classes and 0 <= p < n_classes:
            mat[t][p] += 1
    return mat


def _balanced_accuracy(confusion: list[list[int]]) -> float:
    recalls = []
    for i, row in enumerate(confusion):
        support = sum(row)
        if support == 0:
            continue
        recalls.append(row[i] / support)
    if not recalls:
        return 0.0
    return float(sum(recalls) / len(recalls))

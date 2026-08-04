"""Load a multi-file dataset manifest into training arrays."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def is_manifest_path(path: Path) -> bool:
    if path.is_dir():
        return (path / "dataset.json").is_file()
    return path.is_file() and path.name == "dataset.json"


def load_manifest_dict(path: Path) -> tuple[dict[str, Any], Path]:
    manifest_file = path / "dataset.json" if path.is_dir() else path
    root = manifest_file.parent
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    return data, root


def prepare_from_dataset(
    path: Path,
    *,
    seed: int,
    prepare_file,
) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any], np.ndarray | None]:
    """Return X, y, data_mode, meta, member_roles (per-trial role or None).

    *prepare_file* is train._prepare_arrays(path, seed=...).
    """
    data, root = load_manifest_dict(path)
    members = data.get("members") or []
    split = data.get("split") or {}
    split_mode = str(split.get("mode") or "stratified")
    val_fraction = float(split.get("val_fraction") or 0.2)

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    roles: list[str | None] = []
    class_names: list[str] = []
    name_to_idx: dict[str, int] = {}
    warnings: list[str] = list((data.get("meta") or {}).get("warnings") or [])
    loaded = 0

    for member in members:
        rel = str(member.get("path") or "")
        member_path = (root / rel).resolve()
        if not member_path.is_file():
            warnings.append(f"Missing member: {rel}")
            continue
        role = member.get("role")
        # Per-class trial files are valid as members; ≥2 classes is enforced globally.
        try:
            x, y, mode, meta = prepare_file(
                member_path, seed=seed, allow_single_class=True
            )
        except TypeError:
            x, y, mode, meta = prepare_file(member_path, seed=seed)
        if mode == "synthetic_demo":
            warnings.append(f"No labels in {rel}")
            continue
        # Remap class names into a global index space.
        local_names = list(meta.get("class_names") or [])
        mapped = np.zeros_like(y)
        for i, label in enumerate(y):
            name = local_names[int(label)] if int(label) < len(local_names) else f"class_{int(label)}"
            if name not in name_to_idx:
                name_to_idx[name] = len(class_names)
                class_names.append(name)
            mapped[i] = name_to_idx[name]
        xs.append(x)
        ys.append(mapped.astype(np.int64))
        roles.extend([role] * len(mapped))
        loaded += 1

    if not xs:
        meta = {
            "source": str(path),
            "dataset": data.get("name"),
            "warnings": warnings,
            "note": "No labeled members in dataset",
        }
        return (
            np.zeros((0, 1, 1, 1), dtype=np.float32),
            np.zeros((0,), dtype=np.int64),
            "synthetic_demo",
            meta,
            None,
        )

    # Align channel/time dims (truncate to min shared)
    chans = {a.shape[2] for a in xs}
    times = {a.shape[3] for a in xs}
    if len(chans) > 1:
        warnings.append("Channel counts differed across members; truncated to shared set")
    if len(times) > 1:
        warnings.append("Window lengths differed across members; truncated to shortest")
    min_c = min(a.shape[2] for a in xs)
    min_t = min(a.shape[3] for a in xs)
    xs = [a[:, :, :min_c, :min_t] for a in xs]
    x_all = np.concatenate(xs, axis=0)
    y_all = np.concatenate(ys, axis=0)
    role_arr = np.asarray(roles, dtype=object)

    meta = {
        "source": str(path),
        "dataset": data.get("name"),
        "data_mode": "dataset",
        "label_source": (data.get("label") or {}).get("source"),
        "n_members_loaded": loaded,
        "n_members": len(members),
        "n_samples": int(x_all.shape[0]),
        "n_channels": int(x_all.shape[2]),
        "n_times": int(x_all.shape[3]),
        "n_classes": int(len(np.unique(y_all))),
        "class_names": class_names,
        "split_mode": split_mode,
        "val_fraction": val_fraction,
        "warnings": warnings,
        "sfreq": (data.get("meta") or {}).get("sfreq"),
    }
    return x_all, y_all, "labeled_dataset", meta, role_arr


def split_indices(
    y: np.ndarray,
    *,
    seed: int,
    split_mode: str,
    val_fraction: float,
    roles: np.ndarray | None,
    stratified_split,
) -> tuple[np.ndarray, np.ndarray]:
    """Choose train/val indices from dataset split config."""
    if (
        split_mode == "by_member_role"
        and roles is not None
        and any(r is not None for r in roles)
    ):
        train_idx = np.flatnonzero(np.array([r in (None, "train") for r in roles]))
        test_idx = np.flatnonzero(np.array([r == "test" for r in roles]))
        # Members without role go to train; if no explicit test, fall back.
        if len(test_idx) >= 1 and len(train_idx) >= 1:
            # Use test role as validation holdout
            return train_idx, test_idx
    train_frac = max(0.5, min(0.95, 1.0 - float(val_fraction)))
    return stratified_split(y, seed=seed, train_frac=train_frac)

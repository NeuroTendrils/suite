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
) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any], dict[str, Any]]:
    """Return X, y, data_mode, meta, split_ctx {roles, groups}.

    *prepare_file* is train._prepare_arrays(path, seed=...).
    """
    data, root = load_manifest_dict(path)
    members = data.get("members") or []
    split = data.get("split") or {}
    split_mode = str(split.get("mode") or "by_group")
    val_fraction = float(split.get("val_fraction") or 0.2)

    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    roles: list[str | None] = []
    groups: list[str] = []
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
        # Prefer explicit subject (Study), then group, then member id.
        group = str(
            member.get("subject") or member.get("group") or member.get("id") or rel
        )
        try:
            x, y, mode, meta = prepare_file(
                member_path, seed=seed, allow_single_class=True
            )
        except TypeError:
            x, y, mode, meta = prepare_file(member_path, seed=seed)
        if mode == "synthetic_demo":
            warnings.append(f"No labels in {rel}")
            continue
        local_names = list(meta.get("class_names") or [])
        mapped = np.zeros_like(y)
        for i, label in enumerate(y):
            name = (
                local_names[int(label)]
                if int(label) < len(local_names)
                else f"class_{int(label)}"
            )
            if name not in name_to_idx:
                name_to_idx[name] = len(class_names)
                class_names.append(name)
            mapped[i] = name_to_idx[name]
        xs.append(x)
        ys.append(mapped.astype(np.int64))
        roles.extend([role] * len(mapped))
        groups.extend([group] * len(mapped))
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
            {"roles": None, "groups": None},
        )

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
    group_arr = np.asarray(groups, dtype=object)

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
        "n_groups": int(len(set(groups))),
    }
    return (
        x_all,
        y_all,
        "labeled_dataset",
        meta,
        {"roles": role_arr, "groups": group_arr},
    )


def _temporal_within_group_split(
    groups: np.ndarray, *, val_fraction: float
) -> tuple[np.ndarray, np.ndarray]:
    """Hold out the last val_fraction of each group's samples (time order).

    Prevents adjacent windows from the same trial landing in both splits.
    """
    train_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []
    for group in sorted(set(groups.tolist()), key=str):
        idx = np.flatnonzero(groups == group)
        if len(idx) == 1:
            train_parts.append(idx)
            continue
        # Keep order within the group (window index order from concat).
        n_val = max(1, int(round(float(val_fraction) * len(idx))))
        n_val = min(n_val, len(idx) - 1)
        train_parts.append(idx[:-n_val])
        val_parts.append(idx[-n_val:])
    train_idx = np.concatenate(train_parts) if train_parts else np.array([], dtype=int)
    val_idx = np.concatenate(val_parts) if val_parts else train_idx[:1]
    return train_idx, val_idx


def _by_group_split(
    y: np.ndarray,
    groups: np.ndarray,
    *,
    seed: int,
    val_fraction: float,
) -> tuple[np.ndarray, np.ndarray, str]:
    """Assign whole groups to train/val. Falls back to temporal-within-group."""
    rng = np.random.default_rng(seed)
    unique_groups = sorted(set(groups.tolist()), key=str)

    # Majority class per group (for stratified group assignment).
    group_class: dict[Any, int] = {}
    class_groups: dict[int, list[Any]] = {}
    for group in unique_groups:
        idx = np.flatnonzero(groups == group)
        labels, counts = np.unique(y[idx], return_counts=True)
        maj = int(labels[int(np.argmax(counts))])
        group_class[group] = maj
        class_groups.setdefault(maj, []).append(group)

    # Need ≥2 groups for at least one class to hold out a whole group safely.
    can_holdout = any(len(gs) >= 2 for gs in class_groups.values())
    if not can_holdout or len(unique_groups) < 2:
        return (
            *_temporal_within_group_split(groups, val_fraction=val_fraction),
            "temporal_within_group",
        )

    val_groups: set[Any] = set()
    for _cls, gs in class_groups.items():
        gs = list(gs)
        rng.shuffle(gs)
        if len(gs) == 1:
            continue  # keep sole group of this class in train
        n_val = max(1, int(round(float(val_fraction) * len(gs))))
        n_val = min(n_val, len(gs) - 1)
        val_groups.update(gs[:n_val])

    if not val_groups:
        return (
            *_temporal_within_group_split(groups, val_fraction=val_fraction),
            "temporal_within_group",
        )

    train_idx = np.flatnonzero(np.array([g not in val_groups for g in groups]))
    val_idx = np.flatnonzero(np.array([g in val_groups for g in groups]))
    if len(train_idx) < 1 or len(val_idx) < 1:
        return (
            *_temporal_within_group_split(groups, val_fraction=val_fraction),
            "temporal_within_group",
        )
    return train_idx, val_idx, "by_group"


def split_indices(
    y: np.ndarray,
    *,
    seed: int,
    split_mode: str,
    val_fraction: float,
    roles: np.ndarray | None = None,
    groups: np.ndarray | None = None,
    stratified_split=None,
) -> tuple[np.ndarray, np.ndarray, str]:
    """Choose train/val indices. Returns (train_idx, val_idx, resolved_mode)."""
    if (
        split_mode == "by_member_role"
        and roles is not None
        and any(r is not None for r in roles)
    ):
        train_idx = np.flatnonzero(np.array([r in (None, "train") for r in roles]))
        test_idx = np.flatnonzero(np.array([r == "test" for r in roles]))
        if len(test_idx) >= 1 and len(train_idx) >= 1:
            return train_idx, test_idx, "by_member_role"

    if split_mode in {"by_group", "temporal_within_group"} and groups is not None:
        if split_mode == "temporal_within_group":
            tr, va = _temporal_within_group_split(groups, val_fraction=val_fraction)
            return tr, va, "temporal_within_group"
        tr, va, resolved = _by_group_split(
            y, groups, seed=seed, val_fraction=val_fraction
        )
        return tr, va, resolved

    # Explicit stratified (or unknown mode): window-level — leaky for trial files.
    train_frac = max(0.5, min(0.95, 1.0 - float(val_fraction)))
    if stratified_split is None:
        raise ValueError("stratified_split callable required for stratified mode")
    tr, va = stratified_split(y, seed=seed, train_frac=train_frac)
    return tr, va, "stratified"

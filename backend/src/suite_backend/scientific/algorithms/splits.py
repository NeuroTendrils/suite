"""Phase 16 — leakage-aware train/val/test splits."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.domain.models import DataSplit, MLDataset
from suite_backend.neurostudio.generalization import detect_leakage


def _validate_fractions(dataset: MLDataset, val_frac: float, test_frac: float) -> None:
    if not (np.isfinite(val_frac) and np.isfinite(test_frac) and 0 <= val_frac < 1 and 0 <= test_frac < 1 and val_frac + test_frac < 1):
        raise ValueError("split fractions must be finite, non-negative and leave training samples")
    if len(dataset.subject_ids) != len(dataset.labels):
        raise ValueError("subject ids must match dataset labels")
    if not dataset.labels:
        raise ValueError("cannot split an empty dataset")


def make_subject_split(
    dataset: MLDataset,
    *,
    study_id: str,
    val_frac: float = 0.15,
    test_frac: float = 0.2,
    seed: int = 0,
) -> DataSplit:
    _validate_fractions(dataset, val_frac, test_frac)
    rng = np.random.default_rng(seed)
    subjects = sorted(set(dataset.subject_ids))
    if len(subjects) < 2:
        # fall back to stratified trial split with explicit leakage warning
        return make_stratified_trial_split(
            dataset,
            study_id=study_id,
            val_frac=val_frac,
            test_frac=test_frac,
            seed=seed,
            note="single_subject_fallback",
        )

    order = list(subjects)
    rng.shuffle(order)
    n = len(order)
    n_test = max(1, int(round(n * test_frac))) if test_frac > 0 else 0
    n_val = max(0, int(round(n * val_frac)))
    if n_test + n_val >= n:
        n_val = 0
        n_test = min(n_test, n - 1)
    test_subj = set(order[:n_test])
    val_subj = set(order[n_test : n_test + n_val])
    train_subj = set(order[n_test + n_val :])

    train_idx, val_idx, test_idx = [], [], []
    for i, sid in enumerate(dataset.subject_ids):
        if sid in test_subj:
            test_idx.append(i)
        elif sid in val_subj:
            val_idx.append(i)
        else:
            train_idx.append(i)

    split_def = {
        "train_subjects": sorted(train_subj),
        "val_subjects": sorted(val_subj),
        "test_subjects": sorted(test_subj),
    }
    leakage = detect_leakage(split_def)
    return DataSplit(
        study_id=study_id,
        dataset_id=dataset.id,
        method="subject",
        train_indices=train_idx,
        val_indices=val_idx,
        test_indices=test_idx,
        train_subjects=sorted(train_subj),
        val_subjects=sorted(val_subj),
        test_subjects=sorted(test_subj),
        leakage_check=leakage,
        parameters={"val_frac": val_frac, "test_frac": test_frac, "seed": seed},
    )


def make_stratified_trial_split(
    dataset: MLDataset,
    *,
    study_id: str,
    val_frac: float = 0.15,
    test_frac: float = 0.2,
    seed: int = 0,
    note: str | None = None,
) -> DataSplit:
    _validate_fractions(dataset, val_frac, test_frac)
    rng = np.random.default_rng(seed)
    labels = np.asarray(dataset.labels)
    n = len(labels)
    train_idx: list[int] = []
    val_idx: list[int] = []
    test_idx: list[int] = []
    for lab in sorted(set(labels.tolist())):
        idxs = np.where(labels == lab)[0]
        rng.shuffle(idxs)
        nt = max(1, int(round(len(idxs) * test_frac))) if len(idxs) > 2 and test_frac > 0 else 0
        nv = max(0, int(round(len(idxs) * val_frac))) if len(idxs) > 3 else 0
        if nt + nv >= len(idxs):
            nv = 0
            nt = min(1, len(idxs) - 1) if len(idxs) > 1 else 0
        test_idx.extend(idxs[:nt].tolist())
        val_idx.extend(idxs[nt : nt + nv].tolist())
        train_idx.extend(idxs[nt + nv :].tolist())

    train_subj = sorted({dataset.subject_ids[i] for i in train_idx})
    val_subj = sorted({dataset.subject_ids[i] for i in val_idx})
    test_subj = sorted({dataset.subject_ids[i] for i in test_idx})
    split_def = {
        "train_subjects": train_subj,
        "val_subjects": val_subj,
        "test_subjects": test_subj,
    }
    leakage = detect_leakage(split_def)
    if note == "single_subject_fallback" or (set(train_subj) & set(test_subj)):
        leakage = dict(leakage)
        leakage["ok"] = False
        warnings = list(leakage.get("warnings") or [])
        warnings.append(
            "trial split may leak subject identity — prefer multi-subject subject-wise splits"
        )
        leakage["warnings"] = warnings

    return DataSplit(
        study_id=study_id,
        dataset_id=dataset.id,
        method="stratified_trial",
        train_indices=sorted(train_idx),
        val_indices=sorted(val_idx),
        test_indices=sorted(test_idx),
        train_subjects=train_subj,
        val_subjects=val_subj,
        test_subjects=test_subj,
        leakage_check=leakage,
        parameters={
            "val_frac": val_frac,
            "test_frac": test_frac,
            "seed": seed,
            "note": note,
            "n": n,
        },
    )


def split_definition_dict(split: DataSplit) -> dict[str, Any]:
    return {
        "train_subjects": split.train_subjects,
        "val_subjects": split.val_subjects,
        "test_subjects": split.test_subjects,
        "train_indices": split.train_indices,
        "val_indices": split.val_indices,
        "test_indices": split.test_indices,
        "method": split.method,
    }

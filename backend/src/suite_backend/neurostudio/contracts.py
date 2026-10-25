"""Shared dataset/model contracts: prevent leakage and silent feature reordering."""

from __future__ import annotations

from suite_backend.domain.models import DataSplit, MLDataset


def validate_split(split: DataSplit, dataset: MLDataset, n_samples: int) -> None:
    if split.dataset_id != dataset.id:
        raise ValueError("split belongs to a different dataset")
    parts = [split.train_indices, split.val_indices, split.test_indices]
    seen: set[int] = set()
    for indices in parts:
        if len(indices) != len(set(indices)):
            raise ValueError("split contains duplicate sample indices")
        if any(i < 0 or i >= n_samples for i in indices):
            raise ValueError("split contains out-of-range sample indices")
        if seen.intersection(indices):
            raise ValueError("train, validation and test samples must not overlap")
        seen.update(indices)
    if not split.train_indices:
        raise ValueError("training split is empty")


def validate_features(dataset: MLDataset, expected: list[str], method: str | None = None) -> None:
    if method is not None and dataset.provenance.get("method") != method:
        raise ValueError(
            "feature extraction method mismatch; rebuild with the training feature pipeline"
        )
    if dataset.feature_names != expected:
        raise ValueError("feature names/order mismatch; use the training feature pipeline")

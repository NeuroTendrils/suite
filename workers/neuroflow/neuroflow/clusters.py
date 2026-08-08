"""Cross-subject ICA component clustering (EEGLAB STUDY-style) — Phase 4 scaffold.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from typing import Any

import numpy as np


class ClusterError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def cluster_ica_features(
    features: list[np.ndarray],
    *,
    n_clusters: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    """Cluster per-component feature vectors across subjects.

    *features* is a list of arrays shaped (n_components, n_feature_dims),
    one entry per subject/run. Returns cluster labels per (subject, component).

    v1 uses k-means on concatenated features. Richer dipoles / spectra come later.
    """
    if not features:
        raise ClusterError("invalid_args", "features list is empty")
    if n_clusters < 2:
        raise ClusterError("invalid_args", "n_clusters must be ≥ 2")

    stacked: list[np.ndarray] = []
    index: list[tuple[int, int]] = []
    for si, block in enumerate(features):
        arr = np.asarray(block, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[0] == 0:
            continue
        for ci in range(arr.shape[0]):
            stacked.append(arr[ci])
            index.append((si, ci))
    if len(stacked) < n_clusters:
        raise ClusterError(
            "invalid_data",
            f"need at least {n_clusters} components across subjects; got {len(stacked)}",
        )

    X = np.stack(stacked, axis=0)
    # Normalize features.
    mean = X.mean(axis=0, keepdims=True)
    std = X.std(axis=0, keepdims=True)
    std = np.where(std < 1e-12, 1.0, std)
    Xn = (X - mean) / std

    try:
        from sklearn.cluster import KMeans
    except ImportError as exc:
        raise ClusterError(
            "dependency_missing",
            "scikit-learn is required for clustering",
        ) from exc

    model = KMeans(n_clusters=n_clusters, random_state=seed, n_init=10)
    labels = model.fit_predict(Xn)

    assignments = [
        {"subject_index": int(si), "component": int(ci), "cluster": int(lab)}
        for (si, ci), lab in zip(index, labels.tolist())
    ]
    sizes = {int(c): int(np.sum(labels == c)) for c in range(n_clusters)}
    return {
        "n_clusters": n_clusters,
        "assignments": assignments,
        "cluster_sizes": sizes,
        "inertia": float(model.inertia_),
    }

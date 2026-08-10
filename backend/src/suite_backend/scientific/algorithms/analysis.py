"""Phase 14 — descriptive stats and simple condition comparisons."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from suite_backend.domain.models import AnalysisReport, EpochSet, FeatureSet, Recording


def _welch_t(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    a = np.asarray(a, dtype=np.float64).ravel()
    b = np.asarray(b, dtype=np.float64).ravel()
    if a.size < 2 or b.size < 2:
        return {"t": float("nan"), "df": float("nan"), "p_approx": float("nan")}
    ma, mb = float(np.mean(a)), float(np.mean(b))
    va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    na, nb = a.size, b.size
    se2 = va / na + vb / nb
    if se2 <= 0:
        return {"t": 0.0, "df": float(na + nb - 2), "p_approx": 1.0}
    t = (ma - mb) / np.sqrt(se2)
    # Welch–Satterthwaite df
    num = se2**2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    df = num / den if den > 0 else float(na + nb - 2)
    # crude two-sided p via erfc approximation of normal (ok for smoke / utilitarian UI)
    z = abs(t)
    p = float(math.erfc(z / math.sqrt(2.0)))
    return {"t": float(t), "df": float(df), "p_approx": p, "mean_a": ma, "mean_b": mb}


def descriptive_from_features(
    *,
    study_id: str,
    recording: Recording,
    featureset: FeatureSet,
) -> AnalysisReport:
    X = np.asarray(featureset.values, dtype=np.float64)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    names = list(featureset.feature_names)
    means = np.mean(X, axis=0) if X.size else np.array([])
    stds = np.std(X, axis=0, ddof=1) if X.shape[0] > 1 else np.zeros_like(means)
    table = {
        names[i]: {"mean": float(means[i]), "std": float(stds[i])}
        for i in range(len(names))
    }
    return AnalysisReport(
        study_id=study_id,
        recording_id=recording.id,
        name=f"descriptive_{featureset.kind}",
        kind="descriptive",
        summary={
            "n_rows": int(X.shape[0]),
            "n_features": int(X.shape[1]) if X.ndim == 2 else 0,
            "featureset_id": featureset.id,
        },
        tables={"features": table},
        provenance={"source": "featureset", "featureset_id": featureset.id},
    )


def compare_conditions_from_epochs(
    *,
    study_id: str,
    recording: Recording,
    epochset: EpochSet,
    channel: str | None = None,
) -> AnalysisReport:
    """Compare mean |amplitude| across conditions using epoch FIF when present."""
    import mne

    fif = (epochset.artifact_paths or {}).get("fif") or (epochset.artifact_paths or {}).get(
        "fif_original"
    )
    if not fif:
        return AnalysisReport(
            study_id=study_id,
            recording_id=recording.id,
            name="compare_conditions",
            kind="compare_conditions",
            summary={"status": "no_fif"},
            tests=[],
            provenance={"epochset_id": epochset.id},
        )

    epochs = mne.read_epochs(fif, preload=True, verbose=False)
    keep = [not t.rejected for t in sorted(epochset.trials, key=lambda x: x.index)]
    if len(keep) == len(epochs):
        epochs = epochs[keep]
    ch = channel if channel in epochs.ch_names else epochs.ch_names[0]
    data = epochs.get_data(picks=[ch])[:, 0, :]  # n_epochs × time
    conds = [t.condition or t.event_name or "?" for t in sorted(epochset.trials, key=lambda x: x.index) if not t.rejected]
    if len(conds) != data.shape[0]:
        # fall back to event_id from epochs
        id_to_name = {v: k for k, v in epochs.event_id.items()}
        conds = [id_to_name.get(int(e), str(e)) for e in epochs.events[:, 2]]

    by: dict[str, list[float]] = {}
    for i, c in enumerate(conds):
        by.setdefault(c, []).append(float(np.mean(np.abs(data[i]))))

    keys = sorted(by.keys())
    tests: list[dict[str, Any]] = []
    if len(keys) >= 2:
        stats = _welch_t(np.asarray(by[keys[0]]), np.asarray(by[keys[1]]))
        tests.append(
            {
                "test": "welch_t",
                "channel": ch,
                "condition_a": keys[0],
                "condition_b": keys[1],
                "n_a": len(by[keys[0]]),
                "n_b": len(by[keys[1]]),
                **stats,
            }
        )

    return AnalysisReport(
        study_id=study_id,
        recording_id=recording.id,
        name="compare_conditions",
        kind="compare_conditions",
        summary={
            "channel": ch,
            "conditions": {k: {"n": len(v), "mean_abs": float(np.mean(v))} for k, v in by.items()},
            "epochset_id": epochset.id,
        },
        tests=tests,
        tables={"condition_means": {k: float(np.mean(v)) for k, v in by.items()}},
        provenance={"epochset_id": epochset.id, "channel": ch},
    )

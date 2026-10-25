"""Phase 15 — build tabular ML datasets from epochs / features / multimodal streams."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.domain.models import DataStream, EpochSet, FeatureSet, MLDataset, Modality
from suite_backend.scientific.algorithms.feature_extraction import DEFAULT_BANDS, _bandpower_1d
from suite_backend.scientific.io.canonical import load_stream_samples


def build_from_epochs(
    *,
    study_id: str,
    epochset: EpochSet,
    out_dir: Path,
    name: str = "epochs_bandpower",
) -> MLDataset:
    import mne

    fif = (epochset.artifact_paths or {}).get("fif_original") or (epochset.artifact_paths or {}).get(
        "fif"
    )
    if not fif:
        raise ValueError("epochset has no FIF — recreate with save_fif=True")

    epochs = mne.read_epochs(fif, preload=True, verbose=False)
    trials = sorted(epochset.trials, key=lambda t: t.index)
    keep_mask = [not t.rejected for t in trials]
    if len(keep_mask) == len(epochs):
        epochs = epochs[keep_mask]
        trials = [t for t in trials if not t.rejected]
    else:
        raise ValueError("epoch/trial alignment mismatch; recreate the epoch set")

    if not trials:
        raise ValueError("no accepted epochs remain; review trial rejections")
    epochs.pick("eeg", exclude="bads")
    if not len(epochs.ch_names):
        raise ValueError("no usable EEG channels remain")
    data = epochs.get_data()  # n_ep, n_ch, n_t
    sfreq = float(epochs.info["sfreq"])
    ch_names = list(epochs.ch_names)
    feature_names: list[str] = []
    for ch in ch_names:
        for b in DEFAULT_BANDS:
            feature_names.append(f"{ch}_{b}")

    rows: list[list[float]] = []
    labels: list[str] = []
    subject_ids: list[str] = []
    session_ids: list[str] = []
    trial_ids: list[str] = []
    for i, trial in enumerate(trials):
        if i >= data.shape[0]:
            break
        row: list[float] = []
        for ci, ch in enumerate(ch_names):
            for bname, (lo, hi) in DEFAULT_BANDS.items():
                row.append(_bandpower_1d(data[i, ci], sfreq, lo, hi))
        rows.append(row)
        labels.append(str(trial.condition or trial.event_name or "unknown"))
        subject_ids.append(trial.subject_id)
        session_ids.append(trial.session_id)
        trial_ids.append(trial.id)

    X = np.asarray(rows, dtype=np.float64)
    y = np.asarray(labels)
    out_dir.mkdir(parents=True, exist_ok=True)
    ds = MLDataset(
        study_id=study_id,
        name=name,
        source="epochs",
        epochset_id=epochset.id,
        feature_names=feature_names,
        label_names=sorted(set(labels)),
        n_samples=int(X.shape[0]),
        n_features=int(X.shape[1]) if X.ndim == 2 else 0,
        subject_ids=subject_ids,
        session_ids=session_ids,
        trial_ids=trial_ids,
        labels=labels,
        modalities=["eeg"],
        provenance={"epochset_id": epochset.id, "method": "welch_bandpower_v2"},
    )
    x_path = out_dir / f"{ds.id}_X.npy"
    y_path = out_dir / f"{ds.id}_y.npy"
    np.save(x_path, X)
    np.save(y_path, y)
    ds.paths = {"X": str(x_path), "y": str(y_path)}
    return ds


def build_from_featureset(
    *,
    study_id: str,
    featureset: FeatureSet,
    out_dir: Path,
    name: str = "featureset",
    default_label: str = "recording",
) -> MLDataset:
    X = np.asarray(featureset.values, dtype=np.float64)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    labels = [default_label] * X.shape[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    ds = MLDataset(
        study_id=study_id,
        name=name,
        source="featureset",
        featureset_ids=[featureset.id],
        feature_names=list(featureset.feature_names),
        label_names=[default_label],
        n_samples=int(X.shape[0]),
        n_features=int(X.shape[1]),
        subject_ids=["unknown"] * X.shape[0],
        session_ids=["unknown"] * X.shape[0],
        trial_ids=list(featureset.trial_ids) or [f"row_{i}" for i in range(X.shape[0])],
        labels=labels,
        modalities=["eeg"],
        provenance={"featureset_id": featureset.id},
    )
    x_path = out_dir / f"{ds.id}_X.npy"
    y_path = out_dir / f"{ds.id}_y.npy"
    np.save(x_path, X)
    np.save(y_path, np.asarray(labels))
    ds.paths = {"X": str(x_path), "y": str(y_path)}
    return ds


def build_multimodal(
    *,
    study_id: str,
    epochset: EpochSet,
    streams: list[DataStream],
    out_dir: Path,
    name: str = "multimodal",
    win_sec: float = 0.4,
) -> MLDataset:
    """EEG trial band-power + mean/std of non-EEG streams in the same window."""
    base = build_from_epochs(study_id=study_id, epochset=epochset, out_dir=out_dir, name=name)
    X = np.load(base.paths["X"])
    feature_names = list(base.feature_names)
    extras: list[list[float]] = [[] for _ in range(X.shape[0])]
    modalities = set(base.modalities)

    trials = [t for t in sorted(epochset.trials, key=lambda t: t.index) if not t.rejected]
    for stream in streams:
        mod = stream.modality.value if isinstance(stream.modality, Modality) else str(stream.modality)
        if mod == "eeg":
            continue
        try:
            samples = load_stream_samples(stream)
        except Exception:
            continue
        modalities.add(mod)
        for i, trial in enumerate(trials):
            if i >= X.shape[0]:
                break
            t0 = trial.onset + trial.tmin
            t1 = min(trial.onset + trial.tmax, t0 + win_sec)
            i0 = max(0, int(t0 * samples.sfreq))
            i1 = min(samples.n_times, int(t1 * samples.sfreq))
            if i1 <= i0:
                i1 = min(samples.n_times, i0 + 1)
            chunk = samples.data[:, i0:i1]
            for ci, ch in enumerate(samples.channel_names):
                fname_m = f"{mod}:{ch}_mean"
                fname_s = f"{mod}:{ch}_std"
                if i == 0:
                    feature_names.extend([fname_m, fname_s])
                extras[i].extend(
                    [
                        float(np.mean(chunk[ci])) if chunk.size else 0.0,
                        float(np.std(chunk[ci])) if chunk.size else 0.0,
                    ]
                )

    if any(extras):
        # pad short rows
        width = max((len(r) for r in extras), default=0)
        for r in extras:
            while len(r) < width:
                r.append(0.0)
        X = np.concatenate([X, np.asarray(extras, dtype=np.float64)], axis=1)

    np.save(base.paths["X"], X)
    base.feature_names = feature_names
    base.n_features = int(X.shape[1])
    base.modalities = sorted(modalities)
    base.source = "multimodal"
    base.name = name
    base.provenance = {**(base.provenance or {}), "external_streams": True}
    return base


def load_xy(dataset: MLDataset) -> tuple[np.ndarray, np.ndarray]:
    X = np.load(dataset.paths["X"])
    y = np.load(dataset.paths["y"], allow_pickle=False)
    if X.ndim != 2 or y.ndim != 1 or len(X) != len(y):
        raise ValueError("dataset requires a 2D feature matrix and one label per row")
    if X.shape[1] != len(dataset.feature_names) or len(set(dataset.feature_names)) != X.shape[1]:
        raise ValueError("dataset feature names must be unique and match the matrix")
    if not np.isfinite(X).all():
        raise ValueError("dataset contains non-finite features; review preprocessing")
    return X, y

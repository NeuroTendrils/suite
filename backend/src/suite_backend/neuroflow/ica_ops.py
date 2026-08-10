from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from suite_backend.domain.models import DataStream, DatasetArtifact, Recording
from suite_backend.neuroflow.signal import load_raw_for_recording


def _rejected_indices(recording: Recording) -> list[int]:
    rejected: set[int] = set()
    for ann in recording.annotations:
        if ann.kind == "ica_component" and ann.label == "reject":
            rejected.update(int(i) for i in ann.component_indices)
        elif ann.kind == "ica_component" and ann.label == "keep":
            for i in ann.component_indices:
                rejected.discard(int(i))
    # last decision wins per component via annotations order — refine with decisions
    for d in recording.decisions:
        if d.target_kind != "ica_component":
            continue
        try:
            idx = int(d.target_id)
        except (TypeError, ValueError):
            continue
        if d.action == "reject":
            rejected.add(idx)
        elif d.action == "keep":
            rejected.discard(idx)
    return sorted(rejected)


def _fit_ica(raw, n_components: int | None):
    from mne.preprocessing import ICA

    try:
        import sklearn  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "ICA requires scikit-learn (FastICA). Install with: pip install scikit-learn"
        ) from exc

    n = n_components or min(20, len(raw.ch_names))
    ica = ICA(n_components=n, method="fastica", random_state=97, max_iter="auto")
    ica.fit(raw, verbose=False)
    return ica


def apply_ica_rejection(
    recording: Recording,
    *,
    study_id: str,
    artifact_dir: Path,
    streams: list[DataStream] | None = None,
    n_components: int | None = 20,
    exclude: list[int] | None = None,
) -> dict[str, Any]:
    """Remove rejected ICs and write a new FIF artifact (source raw untouched)."""
    raw = load_raw_for_recording(recording, streams).copy().load_data()
    fit_raw = raw.copy().filter(l_freq=1.0, h_freq=None, verbose=False)
    ica = _fit_ica(fit_raw, n_components)
    ex = exclude if exclude is not None else _rejected_indices(recording)
    ex = [i for i in ex if 0 <= i < ica.n_components_]
    ica.exclude = list(ex)
    cleaned = raw.copy()
    ica.apply(cleaned, verbose=False)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    out = artifact_dir / f"ica_applied_{recording.id}_raw.fif"
    cleaned.save(out, overwrite=True, verbose=False)
    checksum = hashlib.sha256(out.read_bytes()).hexdigest()
    artifact = DatasetArtifact(
        type="cleaned_recording",
        parent_id=recording.artifact_id,
        source=recording.id,
        operation="ica_apply",
        parameters={"exclude": ex, "n_components": ica.n_components_, "method": "fastica"},
        checksum=checksum,
        paths={"fif": str(out)},
        recording_id=recording.id,
        study_id=study_id,
    )
    return {
        "artifact": artifact,
        "excluded": ex,
        "n_components": ica.n_components_,
        "fif": str(out),
    }


def list_ica_components(
    recording: Recording,
    *,
    n_components: int | None = 20,
    streams: list[DataStream] | None = None,
) -> dict[str, Any]:
    """Fit ICA (MNE FastICA) and return utilitarian component summaries."""
    import numpy as np

    raw = load_raw_for_recording(recording, streams)
    raw = raw.copy().filter(l_freq=1.0, h_freq=None, verbose=False)
    ica = _fit_ica(raw, n_components)

    rejected = set(_rejected_indices(recording))

    components = []
    sources = ica.get_sources(raw).get_data()
    times = raw.times
    step = max(1, times.size // 800)
    for idx in range(ica.n_components_):
        ts = sources[idx]
        # crude spectrum via FFT magnitude
        spectrum = np.abs(np.fft.rfft(ts - ts.mean()))
        freqs = np.fft.rfftfreq(ts.size, d=1.0 / raw.info["sfreq"])
        keep = freqs <= 50
        components.append(
            {
                "index": idx,
                "variance_explained": None,
                "rejected": idx in rejected,
                "spectrum_freqs": freqs[keep].astype(float).tolist()[:: max(1, keep.sum() // 64)],
                "spectrum_power": spectrum[keep].astype(float).tolist()[:: max(1, keep.sum() // 64)],
                "timeseries_times": times[::step].astype(float).tolist(),
                "timeseries_preview": ts[::step].astype(float).tolist(),
            }
        )

    # topo data as sensor values for first few components
    maps = []
    for idx in range(min(8, ica.n_components_)):
        maps.append(
            {
                "index": idx,
                "channels": list(raw.ch_names),
                "weights": ica.get_components()[:, idx].astype(float).tolist(),
            }
        )

    return {
        "recording_id": recording.id,
        "n_components": ica.n_components_,
        "components": components,
        "maps": maps,
    }

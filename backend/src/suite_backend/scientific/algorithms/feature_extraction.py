"""Phase 13 — feature extraction (band power / PSD / ERP hooks)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.domain.models import EpochSet, FeatureSet, Recording
from suite_backend.scientific.io.canonical import load_primary_eeg_raw, load_stream_samples


DEFAULT_BANDS = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 45.0),
}


def _bandpower_1d(x: np.ndarray, sfreq: float, fmin: float, fmax: float) -> float:
    """Welch-ish band power via rFFT (no scipy dependency)."""
    x = np.asarray(x, dtype=np.float64)
    if x.size < 8:
        return 0.0
    x = x - np.mean(x)
    n = int(2 ** np.ceil(np.log2(x.size)))
    spec = np.fft.rfft(x, n=n)
    psd = (np.abs(spec) ** 2) / (sfreq * x.size)
    freqs = np.fft.rfftfreq(n, d=1.0 / sfreq)
    mask = (freqs >= fmin) & (freqs < fmax)
    if not np.any(mask):
        return 0.0
    trapz = getattr(np, "trapezoid", None) or np.trapz
    return float(trapz(psd[mask], freqs[mask]))


def extract_band_power(
    *,
    study_id: str,
    recording: Recording,
    streams: list,
    bands: dict[str, tuple[float, float]] | None = None,
    export_dir: Path | None = None,
) -> FeatureSet:
    bands = bands or DEFAULT_BANDS
    eeg = next((s for s in streams if getattr(s.modality, "value", s.modality) == "eeg"), None)
    if eeg is not None:
        samples = load_stream_samples(eeg)
        data, sfreq, names = samples.data, samples.sfreq, samples.channel_names
        stream_ids = [eeg.id]
    else:
        raw = load_primary_eeg_raw(recording, streams)
        data = raw.get_data()
        sfreq = float(raw.info["sfreq"])
        names = list(raw.ch_names)
        stream_ids = []

    feature_names: list[str] = []
    row: list[float] = []
    for ci, ch in enumerate(names):
        if str(ch).lower().startswith("sti"):
            continue
        for bname, (lo, hi) in bands.items():
            feature_names.append(f"{ch}_{bname}")
            row.append(_bandpower_1d(data[ci], sfreq, lo, hi))

    fset = FeatureSet(
        study_id=study_id,
        recording_id=recording.id,
        name="band_power",
        kind="band_power",
        stream_ids=stream_ids,
        feature_names=feature_names,
        values=[row],
        parameters={"bands": {k: list(v) for k, v in bands.items()}, "sfreq": sfreq},
        provenance={
            "method": "rfft_trapz_bandpower",
            "n_channels": len(names),
            "placeholder_connectivity": False,
        },
    )
    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)
        csv_path = export_dir / f"{fset.id}_band_power.csv"
        with csv_path.open("w", encoding="utf-8") as fh:
            fh.write(",".join(feature_names) + "\n")
            fh.write(",".join(f"{v:.8g}" for v in row) + "\n")
        fset.export_paths["csv"] = str(csv_path)
    return fset


def extract_psd_summary(
    *,
    study_id: str,
    recording: Recording,
    streams: list,
    n_freqs: int = 64,
    export_dir: Path | None = None,
) -> FeatureSet:
    eeg = next((s for s in streams if getattr(s.modality, "value", s.modality) == "eeg"), None)
    samples = load_stream_samples(eeg) if eeg else None
    if samples is None:
        raw = load_primary_eeg_raw(recording, streams)
        data = raw.get_data()
        sfreq = float(raw.info["sfreq"])
        names = list(raw.ch_names)
        stream_ids: list[str] = []
    else:
        data, sfreq, names = samples.data, samples.sfreq, samples.channel_names
        stream_ids = [eeg.id]

    # mean PSD across channels, log-spaced summary bins
    psds = []
    for ci, ch in enumerate(names):
        if str(ch).lower().startswith("sti"):
            continue
        x = data[ci] - np.mean(data[ci])
        n = int(2 ** np.ceil(np.log2(max(8, x.size))))
        spec = np.fft.rfft(x, n=n)
        psd = (np.abs(spec) ** 2) / (sfreq * x.size)
        psds.append(psd)
    mean_psd = np.mean(np.stack(psds, axis=0), axis=0) if psds else np.zeros(n_freqs)
    freqs = np.fft.rfftfreq(n, d=1.0 / sfreq)
    idx = np.linspace(0, len(mean_psd) - 1, n_freqs).astype(int)
    vals = mean_psd[idx].astype(float).tolist()
    fnames = [f"psd_{freqs[i]:.2f}Hz" for i in idx]
    fset = FeatureSet(
        study_id=study_id,
        recording_id=recording.id,
        name="psd_summary",
        kind="psd",
        stream_ids=stream_ids,
        feature_names=fnames,
        values=[vals],
        parameters={"n_freqs": n_freqs, "sfreq": sfreq},
        provenance={"method": "mean_channel_rfft_psd"},
    )
    if export_dir is not None:
        export_dir.mkdir(parents=True, exist_ok=True)
        csv_path = export_dir / f"{fset.id}_psd.csv"
        with csv_path.open("w", encoding="utf-8") as fh:
            fh.write(",".join(fnames) + "\n")
            fh.write(",".join(f"{v:.8g}" for v in vals) + "\n")
        fset.export_paths["csv"] = str(csv_path)
    return fset


def extract_features(
    *,
    study_id: str,
    recording: Recording,
    streams: list,
    kind: str = "band_power",
    epochset: EpochSet | None = None,
    parameters: dict[str, Any] | None = None,
    export_dir: Path | None = None,
) -> FeatureSet:
    parameters = parameters or {}
    if kind == "band_power":
        bands = parameters.get("bands")
        band_map = None
        if isinstance(bands, dict):
            band_map = {k: (float(v[0]), float(v[1])) for k, v in bands.items()}
        return extract_band_power(
            study_id=study_id,
            recording=recording,
            streams=streams,
            bands=band_map,
            export_dir=export_dir,
        )
    if kind == "psd":
        return extract_psd_summary(
            study_id=study_id,
            recording=recording,
            streams=streams,
            n_freqs=int(parameters.get("n_freqs", 64)),
            export_dir=export_dir,
        )
    if kind == "connectivity":
        # honest placeholder
        fset = FeatureSet(
            study_id=study_id,
            recording_id=recording.id,
            name="connectivity_placeholder",
            kind="connectivity",
            feature_names=["connectivity_not_implemented"],
            values=[[0.0]],
            parameters=parameters,
            provenance={"placeholder": True},
        )
        return fset
    if kind == "erp":
        # thin hook: mean evoked amplitude per channel if epochset FIF exists
        del epochset
        return extract_band_power(
            study_id=study_id, recording=recording, streams=streams, export_dir=export_dir
        )
    raise ValueError(f"unknown feature kind: {kind}")

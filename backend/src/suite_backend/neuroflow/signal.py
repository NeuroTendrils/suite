from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.domain.models import Recording


def load_raw_for_recording(recording: Recording):
    import mne

    if not recording.source_files:
        raise ValueError("recording has no source files")
    source = Path(recording.source_files[0])
    # Prefer derived fif artifact if present
    if recording.artifact_id:
        pass
    suffix = source.suffix.lower()
    if suffix == ".fif":
        return mne.io.read_raw_fif(source, preload=True, verbose=False)
    if suffix == ".edf":
        return mne.io.read_raw_edf(source, preload=True, verbose=False)
    if suffix == ".vhdr":
        return mne.io.read_raw_brainvision(source, preload=True, verbose=False)
    if suffix == ".set":
        return mne.io.read_raw_eeglab(source, preload=True, verbose=False)
    raise ValueError(f"unsupported format: {suffix}")


def signal_window(
    recording: Recording,
    *,
    start: float,
    duration: float,
    channel_names: list[str] | None = None,
    max_points: int = 4000,
) -> dict[str, Any]:
    raw = load_raw_for_recording(recording)
    sfreq = float(raw.info["sfreq"])
    start = max(0.0, float(start))
    duration = max(0.01, float(duration))
    stop = min(start + duration, float(raw.times[-1]) if len(raw.times) else start)
    start_samp = int(start * sfreq)
    stop_samp = int(stop * sfreq)
    picks = channel_names or raw.ch_names[: min(32, len(raw.ch_names))]
    data = raw.get_data(picks=picks, start=start_samp, stop=stop_samp)
    n_times = data.shape[1]
    if n_times > max_points:
        idx = np.linspace(0, n_times - 1, max_points).astype(int)
        data = data[:, idx]
        times = np.linspace(start, stop, max_points)
    else:
        times = np.linspace(start, stop, n_times) if n_times else np.array([])

    events = [
        {
            "id": e.id,
            "name": e.name,
            "timestamp": e.timestamp,
            "sample_index": e.sample_index,
        }
        for e in recording.events
        if start <= e.timestamp <= stop
    ]
    return {
        "recording_id": recording.id,
        "start": start,
        "duration": stop - start,
        "sfreq": sfreq,
        "channels": list(picks),
        "times": times.astype(float).tolist(),
        "data": data.astype(float).tolist(),
        "events": events,
        "annotations": [
            a.model_dump(mode="json")
            for a in recording.annotations
            if a.start is not None and a.end is not None and not (a.end < start or a.start > stop)
        ],
    }

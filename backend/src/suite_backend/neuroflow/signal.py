from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.domain.models import DataStream, Recording
from suite_backend.scientific.io.canonical import (
    load_primary_eeg_raw,
    load_stream_samples,
)


def load_raw_for_recording(
    recording: Recording, streams: list[DataStream] | None = None
):
    """Canonical EEG Raw loader (FIF / stream samples preferred over vendor path)."""
    return load_primary_eeg_raw(recording, streams)


def signal_window(
    recording: Recording,
    *,
    start: float,
    duration: float,
    channel_names: list[str] | None = None,
    max_points: int = 4000,
    streams: list[DataStream] | None = None,
    stream_id: str | None = None,
) -> dict[str, Any]:
    """
    Window samples from the primary EEG stream, or a specific stream_id (any modality).
    """
    streams = streams or []
    if stream_id:
        stream = next((s for s in streams if s.id == stream_id), None)
        if stream is None:
            raise KeyError(f"stream not found: {stream_id}")
        samples = load_stream_samples(stream)
        sfreq = samples.sfreq
        start = max(0.0, float(start))
        duration = max(0.01, float(duration))
        stop = min(start + duration, float(samples.times[-1]) if len(samples.times) else start)
        start_samp = int(start * sfreq)
        stop_samp = int(stop * sfreq)
        names = channel_names or samples.channel_names[: min(32, len(samples.channel_names))]
        name_to_idx = {n: i for i, n in enumerate(samples.channel_names)}
        idxs = [name_to_idx[n] for n in names if n in name_to_idx]
        data = samples.data[idxs, start_samp:stop_samp]
        n_times = data.shape[1]
        if n_times > max_points:
            idx = np.linspace(0, n_times - 1, max_points).astype(int)
            data = data[:, idx]
            times = np.linspace(start, stop, max_points)
        else:
            times = np.linspace(start, stop, n_times) if n_times else np.array([])
        return {
            "recording_id": recording.id,
            "stream_id": stream.id,
            "modality": stream.modality.value,
            "start": start,
            "duration": stop - start,
            "sfreq": sfreq,
            "units": stream.units,
            "channels": [samples.channel_names[i] for i in idxs],
            "times": times.astype(float).tolist(),
            "data": data.astype(float).tolist(),
            "events": [
                {
                    "id": e.id,
                    "name": e.name,
                    "timestamp": e.timestamp,
                    "sample_index": e.sample_index,
                }
                for e in (stream.events or recording.events)
                if start <= e.timestamp <= stop
            ],
            "annotations": [
                a.model_dump(mode="json")
                for a in (stream.annotations or recording.annotations)
                if a.start is not None
                and a.end is not None
                and not (a.end < start or a.start > stop)
            ],
        }

    raw = load_raw_for_recording(recording, streams)
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

    primary_id = next((s.id for s in streams if s.modality.value == "eeg"), None)
    return {
        "recording_id": recording.id,
        "stream_id": primary_id,
        "modality": "eeg",
        "start": start,
        "duration": stop - start,
        "sfreq": sfreq,
        "units": "uV",
        "channels": list(picks),
        "times": times.astype(float).tolist(),
        "data": data.astype(float).tolist(),
        "events": [
            {
                "id": e.id,
                "name": e.name,
                "timestamp": e.timestamp,
                "sample_index": e.sample_index,
            }
            for e in recording.events
            if start <= e.timestamp <= stop
        ],
        "annotations": [
            a.model_dump(mode="json")
            for a in recording.annotations
            if a.start is not None and a.end is not None and not (a.end < start or a.start > stop)
        ],
    }

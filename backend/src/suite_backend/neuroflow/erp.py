from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.domain.models import DataStream, Recording
from suite_backend.neuroflow.signal import load_raw_for_recording


def _build_epochs(
    recording: Recording,
    *,
    event_name: str | None,
    tmin: float,
    tmax: float,
    baseline: tuple[float | None, float | None],
    streams: list[DataStream] | None,
):
    import mne

    raw = load_raw_for_recording(recording, streams)
    events, event_id = mne.events_from_annotations(raw, verbose=False)
    if not len(events):
        return None, None, None
    if event_name and event_name in event_id:
        use_id = {event_name: event_id[event_name]}
    else:
        use_id = event_id
    epochs = mne.Epochs(
        raw,
        events,
        event_id=use_id,
        tmin=tmin,
        tmax=tmax,
        baseline=baseline,
        preload=True,
        verbose=False,
    )
    return epochs, use_id, raw


def compute_erp(
    recording: Recording,
    *,
    event_name: str | None = None,
    tmin: float = -0.2,
    tmax: float = 0.8,
    baseline: tuple[float | None, float | None] = (None, 0),
    streams: list[DataStream] | None = None,
    erpimage_channel: str | None = None,
    max_trials: int = 80,
) -> dict[str, Any]:
    epochs, use_id, _raw = _build_epochs(
        recording,
        event_name=event_name,
        tmin=tmin,
        tmax=tmax,
        baseline=baseline,
        streams=streams,
    )
    if epochs is None:
        return {
            "status": "no_events",
            "times": [],
            "channels": [],
            "data": [],
            "erpimage": None,
        }
    evoked = epochs.average()
    out: dict[str, Any] = {
        "status": "ok",
        "recording_id": recording.id,
        "event_id": use_id,
        "nave": int(evoked.nave),
        "times": evoked.times.astype(float).tolist(),
        "channels": list(evoked.ch_names),
        "data": evoked.data.astype(float).tolist(),
        "erpimage": None,
    }

    ch = erpimage_channel or (evoked.ch_names[0] if evoked.ch_names else None)
    if ch and ch in epochs.ch_names:
        picks = [epochs.ch_names.index(ch)]
        # (n_epochs, n_times)
        trial_data = epochs.get_data(picks=picks)[:, 0, :]
        n = min(int(max_trials), trial_data.shape[0])
        img = trial_data[:n]
        # downsample time for UI payload
        n_t = img.shape[1]
        step = max(1, n_t // 200)
        times = epochs.times[::step]
        img_ds = img[:, ::step]
        out["erpimage"] = {
            "channel": ch,
            "n_trials": int(n),
            "times": times.astype(float).tolist(),
            "trials": img_ds.astype(float).tolist(),
            "vmin": float(np.percentile(img_ds, 5)),
            "vmax": float(np.percentile(img_ds, 95)),
        }
    return out

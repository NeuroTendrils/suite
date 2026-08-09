from __future__ import annotations

from typing import Any

from suite_backend.domain.models import Recording
from suite_backend.neuroflow.signal import load_raw_for_recording


def compute_erp(
    recording: Recording,
    *,
    event_name: str | None = None,
    tmin: float = -0.2,
    tmax: float = 0.8,
    baseline: tuple[float | None, float | None] = (None, 0),
) -> dict[str, Any]:
    import mne

    raw = load_raw_for_recording(recording)
    events, event_id = mne.events_from_annotations(raw, verbose=False)
    if not len(events):
        return {
            "status": "no_events",
            "times": [],
            "channels": [],
            "data": [],
        }
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
    evoked = epochs.average()
    return {
        "status": "ok",
        "recording_id": recording.id,
        "event_id": use_id,
        "nave": int(evoked.nave),
        "times": evoked.times.astype(float).tolist(),
        "channels": list(evoked.ch_names),
        "data": evoked.data.astype(float).tolist(),
    }

"""Extract Event markers from MNE Raw stim channels / annotations."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from suite_backend.domain.models import Event

_STIM_NAME = re.compile(
    r"^(marker|markers|trigger|stim|event|events|type|code|sti\s*\d*)$",
    re.IGNORECASE,
)


def events_from_annotations(raw: Any) -> list[Event]:
    import mne

    out: list[Event] = []
    try:
        mne_events, event_id = mne.events_from_annotations(raw, verbose=False)
    except Exception:  # noqa: BLE001
        return out
    if mne_events is None or len(mne_events) == 0:
        return out
    id_to_name = {v: k for k, v in event_id.items()}
    sfreq = float(raw.info["sfreq"])
    for row in mne_events:
        sample = int(row[0])
        code = int(row[2])
        name = id_to_name.get(code, str(code))
        out.append(
            Event(
                timestamp=sample / sfreq,
                sample_index=sample,
                code=str(code),
                name=name,
                source="eeg_trigger",
            )
        )
    return out


def events_from_stim_channels(raw: Any) -> list[Event]:
    """Rising-edge events from stim channels (typical for .txt Marker columns)."""
    import mne

    out: list[Event] = []
    try:
        if len(mne.pick_types(raw.info, stim=True)) == 0:
            return out
        # stim_channel=None → all stim-type channels; shortest_event=1 for single-sample codes
        mne_events = mne.find_events(raw, shortest_event=1, verbose=False)
    except Exception:  # noqa: BLE001
        return out
    sfreq = float(raw.info["sfreq"])
    for row in mne_events:
        sample = int(row[0])
        code = int(row[2])
        out.append(
            Event(
                timestamp=sample / sfreq,
                sample_index=sample,
                code=str(code),
                name=str(code),
                source="stim_channel",
            )
        )
    return out


def extract_events_from_raw(raw: Any) -> list[Event]:
    """Annotations first (EEGLAB .set), then stim-channel edges (.txt Marker)."""
    ann = events_from_annotations(raw)
    if ann:
        return ann
    return events_from_stim_channels(raw)


def apply_events_as_annotations(raw: Any, events: list[Event]) -> Any:
    """Write Event list onto Raw so saved FIF keeps markers for MNE tools."""
    if not events:
        return raw
    import mne

    raw.set_annotations(
        mne.Annotations(
            onset=[e.timestamp for e in events],
            duration=[0.0] * len(events),
            description=[e.name for e in events],
        )
    )
    return raw


def is_stim_channel_name(name: str) -> bool:
    return bool(_STIM_NAME.match((name or "").strip()))


def events_from_stim_series(
    values: np.ndarray,
    times: np.ndarray,
    *,
    channel_name: str = "stim",
) -> list[Event]:
    """
    Detect non-zero value onsets on a stim/marker column (full-rate series).

    Used as a timeline fallback when Recording.events was never populated.
    """
    vals = np.asarray(values, dtype=np.float64).ravel()
    times = np.asarray(times, dtype=np.float64).ravel()
    n = min(len(vals), len(times))
    if n == 0:
        return []
    out: list[Event] = []
    prev = 0.0
    for i in range(n):
        v = float(vals[i])
        if v != prev and v != 0.0:
            code = int(round(v)) if abs(v - round(v)) < 1e-6 else v
            out.append(
                Event(
                    timestamp=float(times[i]),
                    sample_index=i,
                    code=str(code),
                    name=str(code),
                    source=f"stim_channel:{channel_name}",
                )
            )
        prev = v
    return out

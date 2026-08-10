"""Multimodal timeline windowing with sync offsets applied."""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from suite_backend.domain.models import ChannelType, DataStream, Recording, SyncGroup
from suite_backend.neuroflow.sync import offset_map
from suite_backend.scientific.io.canonical import load_stream_samples
from suite_backend.scientific.io.stim_events import (
    events_from_stim_series,
    is_stim_channel_name,
)

_NON_CHANNEL_NAME = re.compile(
    r"^(time|times|timestamp|t|sample|samples|index|latency|stim|trigger)$",
    re.IGNORECASE,
)
_SKIP_TYPES = {ChannelType.TRIGGER, "trigger", "stim"}


def _is_signal_channel(name: str, values: np.ndarray, ch_type: str | None) -> bool:
    """Keep biosignal columns; drop time/index/stim (those are markers, not traces)."""
    if ch_type in _SKIP_TYPES or str(ch_type or "").lower() in {"trigger", "stim"}:
        return False
    if _NON_CHANNEL_NAME.match((name or "").strip()):
        return False
    n = (name or "").strip().lower()
    if n.startswith("sti") and n.replace(" ", "").startswith("sti"):
        return False
    if values.size >= 8:
        d = np.diff(values.astype(np.float64))
        if d.size and np.all(d > 0):
            mean_d = float(np.mean(d))
            if mean_d > 0 and float(np.std(d)) / mean_d < 0.05:
                return False  # monotonic time/index column
    return True


def timeline_window(
    recording: Recording,
    streams: list[DataStream],
    *,
    start: float = 0.0,
    duration: float = 5.0,
    max_points: int = 2000,
    sync_group: SyncGroup | None = None,
    stream_ids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Return aligned windows for multiple streams in the *reference* timeline.

    For each stream, local_time = reference_time - offset.
    """
    offsets = offset_map(sync_group) if sync_group else {s.id: 0.0 for s in streams}
    selected = streams
    if stream_ids:
        wanted = set(stream_ids)
        selected = [s for s in streams if s.id in wanted]

    start = max(0.0, float(start))
    duration = max(0.01, float(duration))
    stop = start + duration

    out_streams: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []

    for stream in selected:
        off = float(offsets.get(stream.id, 0.0))
        try:
            samples = load_stream_samples(stream)
        except Exception as exc:  # noqa: BLE001
            out_streams.append(
                {
                    "stream_id": stream.id,
                    "modality": stream.modality.value,
                    "name": stream.name,
                    "offset_sec": off,
                    "error": str(exc),
                    "channels": [],
                    "times": [],
                    "data": [],
                }
            )
            continue

        # reference window [start, stop] → local [start-off, stop-off]
        local_start = start - off
        local_stop = stop - off
        sfreq = samples.sfreq
        type_by_name = {c.name: c.type for c in stream.channels}

        # If import never stored Events (older .txt), derive markers from stim columns.
        stream_events = list(stream.events)
        if not stream_events:
            for ci, name in enumerate(samples.channel_names):
                ctype = type_by_name.get(name)
                ctype_s = (
                    ctype.value if hasattr(ctype, "value") else (str(ctype) if ctype else None)
                )
                if ctype_s in {"trigger", "stim"} or is_stim_channel_name(name):
                    stream_events.extend(
                        events_from_stim_series(
                            samples.data[ci], samples.times, channel_name=name
                        )
                    )

        # index into samples
        i0 = int(max(0, np.searchsorted(samples.times, local_start, side="left")))
        i1 = int(min(samples.n_times, np.searchsorted(samples.times, local_stop, side="right")))
        if i1 <= i0:
            data = np.zeros((samples.n_channels, 0))
            times_ref = np.array([])
            ch_names = samples.channel_names
        else:
            data = samples.data[:, i0:i1]
            # map local times to reference timeline
            times_ref = samples.times[i0:i1] + off
            ch_names = list(samples.channel_names)
            n_times = data.shape[1]
            if n_times > max_points:
                idx = np.linspace(0, n_times - 1, max_points).astype(int)
                data = data[:, idx]
                times_ref = times_ref[idx]

            # Drop time/stim columns — events are markers, not plotted rows
            keep_idx: list[int] = []
            keep_names: list[str] = []
            for ci, name in enumerate(ch_names):
                if ci >= data.shape[0]:
                    break
                ctype = type_by_name.get(name)
                ctype_s = ctype.value if hasattr(ctype, "value") else (str(ctype) if ctype else None)
                if _is_signal_channel(name, data[ci], ctype_s):
                    keep_idx.append(ci)
                    keep_names.append(name)
            if keep_idx:
                data = data[keep_idx, :]
                ch_names = keep_names
            else:
                data = np.zeros((0, data.shape[1] if data.ndim == 2 else 0))
                ch_names = []

        for e in stream_events:
            t_ref = e.timestamp + off
            if start <= t_ref <= stop:
                all_events.append(
                    {
                        "id": e.id,
                        "name": e.name,
                        "timestamp": t_ref,
                        "stream_id": stream.id,
                        "modality": stream.modality.value,
                        "source": e.source,
                    }
                )
        for a in stream.annotations:
            if a.start is None or a.end is None:
                continue
            a0, a1 = a.start + off, a.end + off
            if not (a1 < start or a0 > stop):
                all_events.append(
                    {
                        "id": a.id,
                        "name": a.label,
                        "timestamp": a0,
                        "end": a1,
                        "stream_id": stream.id,
                        "modality": stream.modality.value,
                        "kind": "annotation",
                    }
                )

        status_by_name = {c.name: c.status.value for c in stream.channels}
        out_streams.append(
            {
                "stream_id": stream.id,
                "modality": stream.modality.value,
                "name": stream.name,
                "offset_sec": off,
                "sfreq": sfreq,
                "units": stream.units,
                "channels": ch_names,
                "channel_status": [status_by_name.get(n, "unknown") for n in ch_names],
                "times": times_ref.astype(float).tolist(),
                "data": data.astype(float).tolist(),
            }
        )

    # recording-level events / artifact annotations (legacy + masks)
    for e in recording.events:
        if start <= e.timestamp <= stop:
            all_events.append(
                {
                    "id": e.id,
                    "name": e.name,
                    "timestamp": e.timestamp,
                    "stream_id": None,
                    "modality": "recording",
                    "source": e.source,
                }
            )
    seen_ann = {a.get("id") for a in all_events if a.get("kind") == "annotation"}
    for a in recording.annotations:
        if a.id in seen_ann:
            continue
        if a.start is None or a.end is None:
            continue
        if a.end < start or a.start > stop:
            continue
        all_events.append(
            {
                "id": a.id,
                "name": a.label,
                "timestamp": a.start,
                "end": a.end,
                "stream_id": a.stream_id,
                "modality": "recording",
                "kind": "annotation",
                "artifact": bool((a.metadata or {}).get("artifact")),
            }
        )

    all_events.sort(key=lambda e: e["timestamp"])
    sync_info = None
    if sync_group:
        sync_info = {
            "sync_group_id": sync_group.id,
            "reference_stream_id": sync_group.reference_stream_id,
            "method": sync_group.method.value,
            "quality": sync_group.quality,
            "links": [l.model_dump(mode="json") for l in sync_group.links],
        }

    return {
        "recording_id": recording.id,
        "start": start,
        "duration": stop - start,
        "streams": out_streams,
        "events": all_events,
        "sync": sync_info,
        "note": "offsets applied to reference timeline; not assumed synchronized without SyncGroup",
    }

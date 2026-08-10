"""Multimodal timeline windowing with sync offsets applied."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.domain.models import DataStream, Recording, SyncGroup
from suite_backend.neuroflow.sync import offset_map
from suite_backend.scientific.io.canonical import load_stream_samples


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
            ch_names = samples.channel_names
            n_times = data.shape[1]
            if n_times > max_points:
                idx = np.linspace(0, n_times - 1, max_points).astype(int)
                data = data[:, idx]
                times_ref = times_ref[idx]

        for e in stream.events:
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

        out_streams.append(
            {
                "stream_id": stream.id,
                "modality": stream.modality.value,
                "name": stream.name,
                "offset_sec": off,
                "sfreq": sfreq,
                "units": stream.units,
                "channels": ch_names,
                "times": times_ref.astype(float).tolist(),
                "data": data.astype(float).tolist(),
            }
        )

    # recording-level events (legacy) at offset 0
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

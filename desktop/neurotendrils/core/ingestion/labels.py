"""Event / trial label helpers for manual prep."""

from __future__ import annotations

from typing import Any

from neurotendrils.core.ingestion.schema import EventsConfig


def remap_annotation_labels(raw: Any, events: EventsConfig) -> Any:
    """Rename annotation descriptions using events.code_map; drop ignore list."""
    ann = getattr(raw, "annotations", None)
    if ann is None or len(ann) == 0:
        return raw

    ignore = {name.lower() for name in events.ignore}
    code_map = {str(k): str(v) for k, v in events.code_map.items()}

    onsets: list[float] = []
    durations: list[float] = []
    descriptions: list[str] = []
    for onset, duration, desc in zip(ann.onset, ann.duration, ann.description):
        key = str(desc)
        if key.lower() in ignore:
            continue
        mapped = code_map.get(key, code_map.get(key.lower(), key))
        onsets.append(float(onset))
        durations.append(float(duration))
        descriptions.append(str(mapped))

    import mne

    raw.set_annotations(
        mne.Annotations(
            onset=onsets,
            duration=durations,
            description=descriptions,
            orig_time=ann.orig_time,
        )
    )
    return raw

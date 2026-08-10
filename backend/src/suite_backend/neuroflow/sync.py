"""Synchronization layer for multimodal DataStreams."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np

from suite_backend.domain.models import (
    DataStream,
    Modality,
    SyncGroup,
    SyncLink,
    SyncMethod,
)
from suite_backend.scientific.io.canonical import load_stream_samples


def _stream_time_span(stream: DataStream) -> tuple[float, float] | None:
    try:
        samples = load_stream_samples(stream)
        if len(samples.times) == 0:
            return None
        return float(samples.times[0]), float(samples.times[-1])
    except Exception:  # noqa: BLE001
        if stream.duration is not None:
            return 0.0, float(stream.duration)
        return None


def _event_times(stream: DataStream) -> np.ndarray:
    return np.asarray([e.timestamp for e in stream.events], dtype=np.float64)


def estimate_trigger_offset(
    reference: DataStream, other: DataStream
) -> tuple[float | None, dict[str, Any]]:
    """Estimate offset via shared event names (median pairwise delta)."""
    ref_by_name: dict[str, list[float]] = {}
    for e in reference.events:
        ref_by_name.setdefault(e.name, []).append(e.timestamp)
    other_by_name: dict[str, list[float]] = {}
    for e in other.events:
        other_by_name.setdefault(e.name, []).append(e.timestamp)
    shared = sorted(set(ref_by_name) & set(other_by_name))
    if not shared:
        return None, {
            "status": "no_shared_triggers",
            "shared_event_names": [],
            "confidence": 0.0,
        }
    deltas: list[float] = []
    for name in shared:
        # pair earliest occurrences
        r = sorted(ref_by_name[name])
        o = sorted(other_by_name[name])
        n = min(len(r), len(o))
        for i in range(n):
            deltas.append(r[i] - o[i])  # offset to add to other → ref
    if not deltas:
        return None, {"status": "no_pairs", "confidence": 0.0}
    arr = np.asarray(deltas, dtype=np.float64)
    offset = float(np.median(arr))
    spread = float(np.std(arr)) if len(arr) > 1 else 0.0
    confidence = float(max(0.0, min(1.0, 1.0 - spread / (abs(offset) + 1.0))))
    return offset, {
        "status": "ok",
        "shared_event_names": shared,
        "n_pairs": len(deltas),
        "offset_sec": offset,
        "spread_sec": spread,
        "confidence": confidence,
    }


def assess_timestamp_overlap(
    reference: DataStream, other: DataStream, offset_sec: float = 0.0
) -> dict[str, Any]:
    """Quality from time-span overlap after applying offset. Does not imply sync."""
    ref_span = _stream_time_span(reference)
    other_span = _stream_time_span(other)
    if not ref_span or not other_span:
        return {
            "status": "unknown_span",
            "overlap_ratio": 0.0,
            "assumed_synchronized": False,
            "warning": "cannot assess overlap without readable samples/duration",
        }
    r0, r1 = ref_span
    o0, o1 = other_span[0] + offset_sec, other_span[1] + offset_sec
    overlap = max(0.0, min(r1, o1) - max(r0, o0))
    union = max(r1, o1) - min(r0, o0)
    ratio = float(overlap / union) if union > 0 else 0.0
    # Similar start times alone are NOT treated as synchronized.
    start_delta = abs((o0) - r0)
    return {
        "status": "ok",
        "overlap_ratio": ratio,
        "overlap_sec": overlap,
        "start_delta_sec": start_delta,
        "assumed_synchronized": False,
        "warning": (
            "similar start times do not imply synchronization"
            if start_delta < 0.05 and ratio > 0.9
            else None
        ),
        "confidence": float(ratio * 0.5),  # overlap alone is weak evidence
    }


def build_sync_group(
    *,
    recording_id: str,
    streams: list[DataStream],
    reference_stream_id: str | None = None,
    method: SyncMethod | str = SyncMethod.SHARED_TRIGGERS,
    manual_offsets: dict[str, float] | None = None,
) -> SyncGroup:
    if not streams:
        raise ValueError("need at least one stream to sync")
    method = SyncMethod(method) if not isinstance(method, SyncMethod) else method
    manual_offsets = manual_offsets or {}

    ref = None
    if reference_stream_id:
        ref = next((s for s in streams if s.id == reference_stream_id), None)
    if ref is None:
        ref = next((s for s in streams if s.modality == Modality.EEG), streams[0])

    links: list[SyncLink] = []
    qualities: list[dict[str, Any]] = []
    for stream in streams:
        if stream.id == ref.id:
            links.append(
                SyncLink(
                    stream_id=stream.id,
                    offset_sec=0.0,
                    method=method,
                    quality={"status": "reference", "confidence": 1.0},
                    manual=False,
                )
            )
            continue

        offset = 0.0
        quality: dict[str, Any] = {}
        is_manual = stream.id in manual_offsets

        if is_manual or method == SyncMethod.MANUAL_OFFSET:
            offset = float(manual_offsets.get(stream.id, 0.0))
            quality = {
                "status": "manual",
                "confidence": 1.0 if is_manual else 0.0,
                "assumed_synchronized": False,
                "warning": "manual offset — verify alignment in timeline viewer",
            }
            link_method = SyncMethod.MANUAL_OFFSET
        elif method == SyncMethod.SHARED_TRIGGERS:
            est, quality = estimate_trigger_offset(ref, stream)
            if est is None:
                # Fall back to assessing unsynchronized overlap at offset 0 — do NOT claim sync
                quality = {
                    **quality,
                    **assess_timestamp_overlap(ref, stream, 0.0),
                    "fallback": "no_shared_triggers_offset_left_at_0",
                }
                offset = 0.0
                link_method = SyncMethod.UNSPECIFIED
            else:
                offset = est
                overlap_q = assess_timestamp_overlap(ref, stream, offset)
                quality = {**quality, "overlap": overlap_q}
                link_method = SyncMethod.SHARED_TRIGGERS
        else:  # TIMESTAMPS
            # Use absolute timestamp alignment if both have timestamp vectors; else assess only
            try:
                ref_s = load_stream_samples(ref)
                oth_s = load_stream_samples(stream)
                # If both have non-zero-starting absolute times, offset = ref_start - other_start
                if abs(ref_s.times[0]) > 1e-6 or abs(oth_s.times[0]) > 1e-6:
                    offset = float(ref_s.times[0] - oth_s.times[0])
                    quality = assess_timestamp_overlap(ref, stream, offset)
                    quality["status"] = "timestamp_align"
                    link_method = SyncMethod.TIMESTAMPS
                else:
                    offset = 0.0
                    quality = assess_timestamp_overlap(ref, stream, 0.0)
                    quality["status"] = "relative_times_only"
                    quality["warning"] = (
                        "both streams appear relative-from-zero; not treating as synchronized"
                    )
                    link_method = SyncMethod.UNSPECIFIED
            except Exception as exc:  # noqa: BLE001
                offset = 0.0
                quality = {"status": "error", "error": str(exc), "confidence": 0.0}
                link_method = SyncMethod.UNSPECIFIED

        if stream.id in manual_offsets:
            offset = float(manual_offsets[stream.id])
            is_manual = True
            link_method = SyncMethod.MANUAL_OFFSET
            quality = {
                **quality,
                "status": "manual",
                "manual_override": True,
                "confidence": 1.0,
            }

        links.append(
            SyncLink(
                stream_id=stream.id,
                offset_sec=offset,
                method=link_method,
                quality=quality,
                manual=is_manual,
            )
        )
        qualities.append(quality)

    confidences = [float(q.get("confidence") or 0.0) for q in qualities if q]
    group_quality = {
        "mean_confidence": float(np.mean(confidences)) if confidences else 0.0,
        "assumed_synchronized": False,
        "n_links": len(links),
        "warning": "streams are not assumed synchronized without explicit method/quality",
    }
    now = datetime.now(timezone.utc)
    return SyncGroup(
        recording_id=recording_id,
        reference_stream_id=ref.id,
        method=method,
        links=links,
        quality=group_quality,
        created_at=now,
        updated_at=now,
    )


def apply_manual_offset(group: SyncGroup, stream_id: str, offset_sec: float) -> SyncGroup:
    found = False
    for link in group.links:
        if link.stream_id == stream_id:
            link.offset_sec = float(offset_sec)
            link.manual = True
            link.method = SyncMethod.MANUAL_OFFSET
            link.quality = {
                **dict(link.quality or {}),
                "status": "manual",
                "manual_override": True,
                "confidence": 1.0,
                "assumed_synchronized": False,
            }
            found = True
    if not found:
        group.links.append(
            SyncLink(
                stream_id=stream_id,
                offset_sec=float(offset_sec),
                method=SyncMethod.MANUAL_OFFSET,
                manual=True,
                quality={"status": "manual", "confidence": 1.0},
            )
        )
    group.method = SyncMethod.MANUAL_OFFSET
    group.updated_at = datetime.now(timezone.utc)
    return group


def offset_map(group: SyncGroup) -> dict[str, float]:
    return {link.stream_id: float(link.offset_sec) for link in group.links}

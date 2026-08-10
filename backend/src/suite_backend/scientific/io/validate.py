"""Validation for streams/recordings/studies — blocking errors vs warnings."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.domain.models import (
    DataStream,
    Recording,
    Study,
    SyncGroup,
    ValidationIssue,
    ValidationReport,
)
from suite_backend.domain.queries import iter_recordings
from suite_backend.scientific.io.canonical import load_stream_samples


def _err(code: str, message: str, **kw: Any) -> ValidationIssue:
    return ValidationIssue(level="error", code=code, message=message, **kw)


def _warn(code: str, message: str, **kw: Any) -> ValidationIssue:
    return ValidationIssue(level="warning", code=code, message=message, **kw)


def validate_stream(stream: DataStream) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    sid = stream.id

    if stream.sampling_rate is None or stream.sampling_rate <= 0:
        errors.append(_err("sfreq_missing", "sampling_rate missing or <= 0", stream_id=sid))
    if not stream.channels:
        errors.append(_err("no_channels", "stream has no channels", stream_id=sid))
    else:
        names = [c.name for c in stream.channels]
        if len(names) != len(set(names)):
            errors.append(_err("duplicate_channel_names", "duplicate channel names", stream_id=sid))
        if any(not (c.unit or stream.units) for c in stream.channels):
            warnings.append(_warn("units_missing", "one or more channels lack units", stream_id=sid))

    paths = stream.sample_paths or {}
    if not paths.get("fif") and not paths.get("data_npy") and not stream.source_files:
        errors.append(_err("no_samples", "no sample_paths or source_files", stream_id=sid))

    try:
        samples = load_stream_samples(stream)
        if samples.n_times <= 0:
            errors.append(_err("empty_samples", "loaded zero samples", stream_id=sid))
        if samples.n_channels != len(stream.channels) and stream.channels:
            warnings.append(
                _warn(
                    "channel_count_mismatch",
                    f"metadata channels={len(stream.channels)} vs data={samples.n_channels}",
                    stream_id=sid,
                )
            )
        if np.isnan(samples.data).any():
            n_nan = int(np.isnan(samples.data).sum())
            warnings.append(
                _warn("nan_values", f"data contains {n_nan} NaN values", stream_id=sid)
            )
        if len(samples.times) > 1:
            dt = np.diff(samples.times)
            if np.any(dt <= 0):
                errors.append(
                    _err("timestamps_not_increasing", "timestamps not strictly increasing", stream_id=sid)
                )
        for ev in stream.events:
            if samples.times.size and (
                ev.timestamp < float(samples.times[0]) - 1e-6
                or ev.timestamp > float(samples.times[-1]) + 1e-6
            ):
                warnings.append(
                    _warn(
                        "event_out_of_range",
                        f"event {ev.name!r} at {ev.timestamp} outside stream span",
                        stream_id=sid,
                        details={"event_id": ev.id},
                    )
                )
    except Exception as exc:  # noqa: BLE001
        errors.append(_err("load_failed", f"cannot load samples: {exc}", stream_id=sid))

    if not (stream.provenance or {}).get("normalized"):
        warnings.append(_warn("not_normalized", "stream not marked normalized", stream_id=sid))

    return ValidationReport(
        ok=len(errors) == 0,
        blocking_errors=errors,
        warnings=warnings,
        scope="stream",
    )


def validate_recording(
    recording: Recording,
    streams: list[DataStream],
    sync_groups: list[SyncGroup] | None = None,
) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    rid = recording.id

    if not streams:
        errors.append(_err("no_streams", "recording has no DataStreams", recording_id=rid))

    for stream in streams:
        if stream.recording_id != recording.id:
            errors.append(
                _err(
                    "stream_recording_mismatch",
                    f"stream {stream.id} recording_id mismatch",
                    stream_id=stream.id,
                    recording_id=rid,
                )
            )
        report = validate_stream(stream)
        errors.extend(report.blocking_errors)
        warnings.extend(report.warnings)

    sfreqs = {s.sampling_rate for s in streams if s.sampling_rate}
    if len(sfreqs) > 1:
        warnings.append(
            _warn(
                "mixed_sfreq",
                f"streams have different sampling rates: {sorted(sfreqs)}",
                recording_id=rid,
            )
        )

    sync_groups = sync_groups or []
    if len(streams) > 1 and not sync_groups and not recording.sync_group_ids:
        warnings.append(
            _warn(
                "no_sync_group",
                "multiple streams present but no SyncGroup — not assumed synchronized",
                recording_id=rid,
            )
        )
    for g in sync_groups:
        conf = float((g.quality or {}).get("mean_confidence") or 0.0)
        if conf < 0.3:
            warnings.append(
                _warn(
                    "low_sync_confidence",
                    f"sync group {g.id} low confidence ({conf:.2f})",
                    recording_id=rid,
                    details={"sync_group_id": g.id},
                )
            )
        if (g.quality or {}).get("assumed_synchronized"):
            errors.append(
                _err(
                    "invalid_sync_assumption",
                    "sync group incorrectly marks assumed_synchronized=True",
                    recording_id=rid,
                )
            )

    # subject isolation sanity
    subject_ids = {s.subject_id for s in streams}
    if len(subject_ids) > 1 or (subject_ids and recording.subject_id not in subject_ids):
        errors.append(
            _err(
                "subject_isolation",
                "stream subject_id does not match recording subject",
                recording_id=rid,
            )
        )

    return ValidationReport(
        ok=len(errors) == 0,
        blocking_errors=errors,
        warnings=warnings,
        scope="recording",
    )


def validate_study(
    study: Study,
    *,
    streams_by_recording: dict[str, list[DataStream]],
    sync_by_recording: dict[str, list[SyncGroup]] | None = None,
) -> ValidationReport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    sync_by_recording = sync_by_recording or {}

    if not study.subjects:
        warnings.append(_warn("no_subjects", "study has no subjects"))

    labels = [s.label for s in study.subjects]
    if len(labels) != len(set(labels)):
        warnings.append(_warn("duplicate_subject_labels", "duplicate subject labels"))

    for subject, session, run, rec in iter_recordings(study):
        streams = streams_by_recording.get(rec.id, [])
        report = validate_recording(rec, streams, sync_by_recording.get(rec.id))
        errors.extend(report.blocking_errors)
        warnings.extend(report.warnings)
        # ensure no cross-subject stream leakage
        for st in streams:
            if st.subject_id != subject.id:
                errors.append(
                    _err(
                        "cross_subject_stream",
                        f"stream {st.id} subject {st.subject_id} != {subject.id}",
                        stream_id=st.id,
                        recording_id=rec.id,
                    )
                )

    return ValidationReport(
        ok=len(errors) == 0,
        blocking_errors=errors,
        warnings=warnings,
        scope="study",
    )

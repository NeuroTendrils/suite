from __future__ import annotations

from collections import Counter

from suite_backend.domain.models import DataStream, InspectionReport, Study
from suite_backend.domain.queries import iter_recordings


def build_study_inspection(
    study: Study, *, streams: list[DataStream] | None = None
) -> InspectionReport:
    rates: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    modalities: Counter[str] = Counter()
    event_types: set[str] = set()
    warnings: list[str] = []
    recordings = 0
    sessions = 0
    stream_list = streams or []

    for subject in study.subjects:
        for session in subject.sessions:
            sessions += 1

    for subject, session, _run, rec in iter_recordings(study):
        recordings += 1
        if rec.sampling_rate is not None:
            rates[str(rec.sampling_rate)] += 1
        channel_counts[str(rec.channel_count)] += 1
        for ev in rec.events:
            event_types.add(ev.name)
        if rec.stream_ids:
            if not any(ch.location for ch in rec.channels):
                warnings.append(
                    f"{subject.label}/{session.name}: missing channel locations ({rec.id})"
                )
        elif not any(ch.location for ch in rec.channels):
            warnings.append(
                f"{subject.label}/{session.name}: missing channel locations ({rec.id})"
            )

    for stream in stream_list:
        modalities[stream.modality.value] += 1
        if stream.sampling_rate is not None:
            rates[str(stream.sampling_rate)] += 1
        channel_counts[str(len(stream.channels))] += 1
        for ev in stream.events:
            event_types.add(ev.name)

    if len(rates) > 1:
        warnings.append("subjects/recordings have different sampling rates")
    if len(channel_counts) > 1:
        warnings.append("subjects/recordings have different channel counts")
    if recordings > 0 and not stream_list:
        warnings.append("no DataStreams attached yet (schema migration may be pending)")

    return InspectionReport(
        study_id=study.id,
        subjects=len(study.subjects),
        sessions=sessions,
        recordings=recordings,
        streams=len(stream_list),
        modalities=dict(modalities),
        sampling_rates=dict(rates),
        channel_counts=dict(channel_counts),
        event_types=sorted(event_types),
        warnings=warnings,
        details={"schema_version": study.schema_version},
    )

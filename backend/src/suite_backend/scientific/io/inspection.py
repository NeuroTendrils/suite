from __future__ import annotations

from collections import Counter

from suite_backend.domain.models import InspectionReport, Study


def build_study_inspection(study: Study) -> InspectionReport:
    rates: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    event_types: set[str] = set()
    warnings: list[str] = []
    recordings = 0
    sessions = 0

    for subject in study.subjects:
        for session in subject.sessions:
            sessions += 1
            for run in session.runs:
                for rec in run.recordings:
                    recordings += 1
                    if rec.sampling_rate is not None:
                        rates[str(rec.sampling_rate)] += 1
                    channel_counts[str(rec.channel_count)] += 1
                    for ev in rec.events:
                        event_types.add(ev.name)
                    if not any(ch.location for ch in rec.channels):
                        warnings.append(
                            f"{subject.label}/{session.name}: missing channel locations ({rec.id})"
                        )

    if len(rates) > 1:
        warnings.append("subjects/recordings have different sampling rates")
    if len(channel_counts) > 1:
        warnings.append("subjects/recordings have different channel counts")

    return InspectionReport(
        study_id=study.id,
        subjects=len(study.subjects),
        sessions=sessions,
        recordings=recordings,
        sampling_rates=dict(rates),
        channel_counts=dict(channel_counts),
        event_types=sorted(event_types),
        warnings=warnings,
    )

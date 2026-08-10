"""Study schema migrations (on-disk → CURRENT_STUDY_SCHEMA_VERSION)."""

from __future__ import annotations

from typing import Any

from suite_backend.domain.models import (
    CURRENT_STUDY_SCHEMA_VERSION,
    DataStream,
    Modality,
    Recording,
    Study,
)


def needs_migration(raw: dict[str, Any]) -> bool:
    return int(raw.get("schema_version", 1)) < CURRENT_STUDY_SCHEMA_VERSION


def migrate_study_dict(raw: dict[str, Any]) -> tuple[Study, list[DataStream]]:
    """
    Migrate a study.json payload to schema v2.

    v1→v2: wrap each Recording's legacy channels/events into an EEG DataStream.
    Returns the Study plus any newly created streams that must be persisted.
    """
    version = int(raw.get("schema_version", 1))
    new_streams: list[DataStream] = []

    if version >= CURRENT_STUDY_SCHEMA_VERSION:
        study = Study.model_validate(raw)
        return study, new_streams

    # Ensure schema_version field exists for pydantic
    raw = dict(raw)
    raw["schema_version"] = CURRENT_STUDY_SCHEMA_VERSION
    if "stream_ids" not in raw:
        raw["stream_ids"] = []

    study = Study.model_validate(raw)
    study_stream_ids = list(study.stream_ids)

    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for recording in run.recordings:
                    if recording.stream_ids:
                        continue
                    stream = _eeg_stream_from_legacy_recording(recording)
                    recording.stream_ids = [stream.id]
                    # Keep legacy mirrors populated
                    if not recording.channels and stream.channels:
                        recording.channels = list(stream.channels)
                        recording.channel_count = len(stream.channels)
                    new_streams.append(stream)
                    if stream.id not in study_stream_ids:
                        study_stream_ids.append(stream.id)

    study.stream_ids = study_stream_ids
    study.schema_version = CURRENT_STUDY_SCHEMA_VERSION
    return study, new_streams


def _eeg_stream_from_legacy_recording(recording: Recording) -> DataStream:
    modality = Modality.EEG
    # If all channels are non-eeg, still label stream eeg for v1 migration simplicity.
    return DataStream(
        recording_id=recording.id,
        subject_id=recording.subject_id,
        session_id=recording.session_id,
        run_id=recording.run_id,
        modality=modality,
        name=recording.name or "eeg",
        source_files=list(recording.source_files),
        source_format=recording.source_format,
        sampling_rate=recording.sampling_rate,
        duration=recording.duration,
        channels=list(recording.channels),
        units="uV",
        events=list(recording.events),
        annotations=list(recording.annotations),
        decisions=list(recording.decisions),
        acquisition_metadata=dict(recording.acquisition_metadata),
        provenance={
            "migrated_from": "recording_legacy_v1",
            "recording_id": recording.id,
        },
        sample_paths={
            **(
                {"fif": recording.source_files[0]}
                if recording.source_files and str(recording.source_files[0]).endswith(".fif")
                else {}
            )
        },
        artifact_id=recording.artifact_id,
    )


def recording_from_stream_rollup(recording: Recording, streams: list[DataStream]) -> Recording:
    """Refresh Recording convenience fields from primary EEG stream if present."""
    primary = next((s for s in streams if s.modality == Modality.EEG), None)
    if primary is None and streams:
        primary = streams[0]
    if primary is None:
        return recording
    recording.sampling_rate = primary.sampling_rate
    recording.duration = primary.duration
    recording.channels = list(primary.channels)
    recording.channel_count = len(primary.channels)
    recording.events = list(primary.events)
    if primary.source_files:
        recording.source_files = list(primary.source_files)
    if primary.source_format:
        recording.source_format = primary.source_format
    return recording

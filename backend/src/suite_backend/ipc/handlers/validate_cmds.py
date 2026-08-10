from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

from suite_backend.app_context import AppContext
from suite_backend.domain.queries import find_recording, iter_recordings
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.io.validate import (
    validate_recording,
    validate_stream,
    validate_study,
)


class ValidateStreamParams(BaseModel):
    study_id: str
    stream_id: str


class ValidateRecordingParams(BaseModel):
    study_id: str
    recording_id: str


class ValidateStudyParams(BaseModel):
    study_id: str


@REGISTRY.register("validate.stream", ValidateStreamParams)
def validate_stream_cmd(params: ValidateStreamParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    stream = ctx.studies.get_stream(params.study_id, params.stream_id)
    report = validate_stream(stream)
    stream.validation = report.model_dump(mode="json")
    ctx.studies.save_stream(params.study_id, stream)
    return report.model_dump(mode="json")


@REGISTRY.register("validate.recording", ValidateRecordingParams)
def validate_recording_cmd(params: ValidateRecordingParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    recording = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=recording.id)
    sync_groups = ctx.studies.list_sync_groups(params.study_id, recording_id=recording.id)
    report = validate_recording(recording, streams, sync_groups)
    # persist summary on recording
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for i, rec in enumerate(run.recordings):
                    if rec.id == recording.id:
                        rec.validation = report.model_dump(mode="json")
                        run.recordings[i] = rec
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    return report.model_dump(mode="json")


@REGISTRY.register("validate.study", ValidateStudyParams)
def validate_study_cmd(params: ValidateStudyParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    streams_by_rec: dict[str, list] = {}
    sync_by_rec: dict[str, list] = {}
    for _s, _ses, _r, rec in iter_recordings(study):
        streams_by_rec[rec.id] = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
        sync_by_rec[rec.id] = ctx.studies.list_sync_groups(params.study_id, recording_id=rec.id)
    report = validate_study(
        study, streams_by_recording=streams_by_rec, sync_by_recording=sync_by_rec
    )
    return report.model_dump(mode="json")

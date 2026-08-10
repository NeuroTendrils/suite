from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Run, Session, Subject, Visibility
from suite_backend.domain.queries import (
    find_session,
    find_subject,
    study_tree_summary,
)
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.io.inspection import build_study_inspection


class StudyCreateParams(BaseModel):
    name: str
    task_name: str | None = None


class StudyGetParams(BaseModel):
    study_id: str


class StudyListParams(BaseModel):
    pass


class SubjectAddParams(BaseModel):
    study_id: str
    label: str
    session_name: str = "session-001"
    run_name: str = "run-001"
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubjectMetadataParams(BaseModel):
    study_id: str
    subject_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    merge: bool = True


class SessionAddParams(BaseModel):
    study_id: str
    subject_id: str
    name: str = "session-001"
    metadata: dict[str, Any] = Field(default_factory=dict)
    create_default_run: bool = True
    run_name: str = "run-001"


class RunAddParams(BaseModel):
    study_id: str
    subject_id: str
    session_id: str
    name: str = "run-001"
    metadata: dict[str, Any] = Field(default_factory=dict)


class StreamListParams(BaseModel):
    study_id: str
    recording_id: str | None = None
    subject_id: str | None = None


class StreamGetParams(BaseModel):
    study_id: str
    stream_id: str


class EventMapParams(BaseModel):
    study_id: str
    mapping: dict[str, str] = Field(default_factory=dict)


class VisibilityParams(BaseModel):
    study_id: str
    visibility: Visibility = Visibility.PRIVATE
    organization_id: str | None = None


def _touch(study) -> None:
    study.updated_at = datetime.now(timezone.utc)


@REGISTRY.register("studies.create", StudyCreateParams)
def studies_create(params: StudyCreateParams, ctx: AppContext) -> dict:
    study = ctx.studies.create_study(params.name, params.task_name)
    return study.model_dump(mode="json")


@REGISTRY.register("studies.list", StudyListParams)
def studies_list(_params: StudyListParams, ctx: AppContext) -> dict:
    return {"studies": [s.model_dump(mode="json") for s in ctx.studies.list_studies()]}


@REGISTRY.register("studies.get", StudyGetParams)
def studies_get(params: StudyGetParams, ctx: AppContext) -> dict:
    return ctx.studies.get_study(params.study_id).model_dump(mode="json")


@REGISTRY.register("studies.tree", StudyGetParams)
def studies_tree(params: StudyGetParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    streams = ctx.studies.list_streams(params.study_id)
    return study_tree_summary(study, streams)


@REGISTRY.register("studies.inspect", StudyGetParams)
def studies_inspect(params: StudyGetParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    streams = ctx.studies.list_streams(params.study_id)
    return build_study_inspection(study, streams=streams).model_dump(mode="json")


@REGISTRY.register("subjects.add", SubjectAddParams)
def subjects_add(params: SubjectAddParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    run = Run(name=params.run_name)
    session = Session(name=params.session_name, runs=[run])
    subject = Subject(label=params.label, sessions=[session], metadata=dict(params.metadata))
    study.subjects.append(subject)
    _touch(study)
    ctx.studies.save_study(study)
    return {
        "study_id": study.id,
        "subject": subject.model_dump(mode="json"),
        "session_id": session.id,
        "run_id": run.id,
    }


@REGISTRY.register("subjects.set_metadata", SubjectMetadataParams)
def subjects_set_metadata(params: SubjectMetadataParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    subject = find_subject(study, params.subject_id)
    if params.merge:
        subject.metadata.update(params.metadata)
    else:
        subject.metadata = dict(params.metadata)
    _touch(study)
    ctx.studies.save_study(study)
    return {"subject_id": subject.id, "metadata": subject.metadata}


@REGISTRY.register("sessions.add", SessionAddParams)
def sessions_add(params: SessionAddParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    subject = find_subject(study, params.subject_id)
    runs = [Run(name=params.run_name)] if params.create_default_run else []
    session = Session(name=params.name, runs=runs, metadata=dict(params.metadata))
    subject.sessions.append(session)
    _touch(study)
    ctx.studies.save_study(study)
    return {
        "study_id": study.id,
        "subject_id": subject.id,
        "session": session.model_dump(mode="json"),
    }


@REGISTRY.register("runs.add", RunAddParams)
def runs_add(params: RunAddParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    session = find_session(study, params.subject_id, params.session_id)
    run = Run(name=params.name, metadata=dict(params.metadata))
    session.runs.append(run)
    _touch(study)
    ctx.studies.save_study(study)
    return {
        "study_id": study.id,
        "subject_id": params.subject_id,
        "session_id": session.id,
        "run": run.model_dump(mode="json"),
    }


@REGISTRY.register("streams.list", StreamListParams)
def streams_list(params: StreamListParams, ctx: AppContext) -> dict:
    # Ensure study exists / migrated
    ctx.studies.get_study(params.study_id)
    streams = ctx.studies.list_streams(
        params.study_id,
        recording_id=params.recording_id,
        subject_id=params.subject_id,
    )
    return {"streams": [s.model_dump(mode="json") for s in streams]}


@REGISTRY.register("streams.get", StreamGetParams)
def streams_get(params: StreamGetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    stream = ctx.studies.get_stream(params.study_id, params.stream_id)
    return stream.model_dump(mode="json")


@REGISTRY.register("studies.set_event_map", EventMapParams)
def set_event_map(params: EventMapParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    study.event_definitions.update(params.mapping)
    _touch(study)
    ctx.studies.save_study(study)
    return {"event_definitions": study.event_definitions}


@REGISTRY.register("studies.set_visibility", VisibilityParams)
def set_visibility(params: VisibilityParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    study.visibility = params.visibility
    study.organization_id = params.organization_id
    _touch(study)
    ctx.studies.save_study(study)
    return {
        "visibility": study.visibility.value,
        "organization_id": study.organization_id,
    }

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import (
    Run,
    Session,
    Subject,
    Visibility,
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


class EventMapParams(BaseModel):
    study_id: str
    mapping: dict[str, str] = Field(default_factory=dict)


class VisibilityParams(BaseModel):
    study_id: str
    visibility: Visibility = Visibility.PRIVATE
    organization_id: str | None = None


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


@REGISTRY.register("studies.inspect", StudyGetParams)
def studies_inspect(params: StudyGetParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    return build_study_inspection(study).model_dump(mode="json")


@REGISTRY.register("subjects.add", SubjectAddParams)
def subjects_add(params: SubjectAddParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    run = Run(name=params.run_name)
    session = Session(name=params.session_name, runs=[run])
    subject = Subject(label=params.label, sessions=[session])
    study.subjects.append(subject)
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    return {
        "study_id": study.id,
        "subject": subject.model_dump(mode="json"),
        "session_id": session.id,
        "run_id": run.id,
    }


@REGISTRY.register("studies.set_event_map", EventMapParams)
def set_event_map(params: EventMapParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    study.event_definitions.update(params.mapping)
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    return {"event_definitions": study.event_definitions}


@REGISTRY.register("studies.set_visibility", VisibilityParams)
def set_visibility(params: VisibilityParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    study.visibility = params.visibility
    study.organization_id = params.organization_id
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    return {
        "visibility": study.visibility.value,
        "organization_id": study.organization_id,
    }

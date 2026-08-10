"""Phase 10 — unified events + annotations CRUD."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Annotation, Event, HumanDecision, Modality
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY


class EventListParams(BaseModel):
    study_id: str
    recording_id: str
    stream_id: str | None = None


class EventCreateParams(BaseModel):
    study_id: str
    recording_id: str
    stream_id: str | None = None
    timestamp: float
    name: str
    code: str | None = None
    duration: float = 0.0
    condition: str | None = None
    source: str = "manual"
    sample_index: int | None = None


class EventDeleteParams(BaseModel):
    study_id: str
    recording_id: str
    event_id: str
    stream_id: str | None = None


class AnnotationListParams(BaseModel):
    study_id: str
    recording_id: str
    stream_id: str | None = None


class AnnotationDeleteParams(BaseModel):
    study_id: str
    recording_id: str
    annotation_id: str


def _stream(ctx: AppContext, study_id: str, recording_id: str, stream_id: str | None):
    streams = ctx.studies.list_streams(study_id, recording_id=recording_id)
    if stream_id:
        return next((s for s in streams if s.id == stream_id), None)
    return next((s for s in streams if s.modality == Modality.EEG), None)


def _persist_rec(ctx: AppContext, study_id: str, rec) -> None:
    study = ctx.studies.get_study(study_id)
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for i, r in enumerate(run.recordings):
                    if r.id == rec.id:
                        run.recordings[i] = rec
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)


@REGISTRY.register("events.list", EventListParams)
def events_list(params: EventListParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _stream(ctx, params.study_id, rec.id, params.stream_id)
    # map study event_definitions onto display names
    defs = study.event_definitions or {}
    events = list(stream.events) if stream else list(rec.events)
    out = []
    for e in events:
        d = e.model_dump(mode="json")
        if e.code and e.code in defs:
            d["mapped_name"] = defs[e.code]
        elif e.name in defs:
            d["mapped_name"] = defs[e.name]
        else:
            d["mapped_name"] = e.name
        out.append(d)
    # also include recording-level if stream selected and empty of overlap
    if stream:
        seen = {e["id"] for e in out}
        for e in rec.events:
            if e.id not in seen:
                d = e.model_dump(mode="json")
                d["mapped_name"] = defs.get(e.code or "", defs.get(e.name, e.name))
                out.append(d)
    out.sort(key=lambda x: x["timestamp"])
    return {"events": out, "event_definitions": defs}


@REGISTRY.register("events.create", EventCreateParams)
def events_create(params: EventCreateParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _stream(ctx, params.study_id, rec.id, params.stream_id)
    sfreq = (stream.sampling_rate if stream else rec.sampling_rate) or 1.0
    sample = params.sample_index
    if sample is None:
        sample = int(round(params.timestamp * float(sfreq)))
    # apply study event map for name if code maps
    name = params.name
    if params.code and params.code in (study.event_definitions or {}):
        name = study.event_definitions[params.code]
    ev = Event(
        timestamp=float(params.timestamp),
        sample_index=int(sample),
        duration=float(params.duration),
        code=params.code,
        name=name,
        condition=params.condition,
        stream_id=stream.id if stream else None,
        source=params.source,
    )
    if stream:
        stream.events.append(ev)
        stream.decisions.append(
            HumanDecision(
                target_kind="event",
                target_id=ev.id,
                action="label",
                label=ev.name,
                reason="events.create",
            )
        )
        ctx.studies.save_stream(params.study_id, stream)
    rec.events.append(ev)
    rec.decisions.append(
        HumanDecision(
            target_kind="event",
            target_id=ev.id,
            action="label",
            label=ev.name,
            reason="events.create",
        )
    )
    _persist_rec(ctx, params.study_id, rec)
    return {"event": ev.model_dump(mode="json")}


@REGISTRY.register("events.delete", EventDeleteParams)
def events_delete(params: EventDeleteParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _stream(ctx, params.study_id, rec.id, params.stream_id)
    before = len(rec.events)
    rec.events = [e for e in rec.events if e.id != params.event_id]
    if stream:
        stream.events = [e for e in stream.events if e.id != params.event_id]
        stream.decisions.append(
            HumanDecision(
                target_kind="event",
                target_id=params.event_id,
                action="reject",
                reason="events.delete",
            )
        )
        ctx.studies.save_stream(params.study_id, stream)
    rec.decisions.append(
        HumanDecision(
            target_kind="event",
            target_id=params.event_id,
            action="reject",
            reason="events.delete",
        )
    )
    _persist_rec(ctx, params.study_id, rec)
    return {"deleted": params.event_id, "removed": before - len(rec.events)}


@REGISTRY.register("annotations.list", AnnotationListParams)
def annotations_list(params: AnnotationListParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _stream(ctx, params.study_id, rec.id, params.stream_id)
    anns = list(stream.annotations) if stream and stream.annotations else list(rec.annotations)
    return {"annotations": [a.model_dump(mode="json") for a in anns]}


@REGISTRY.register("annotations.delete", AnnotationDeleteParams)
def annotations_delete(params: AnnotationDeleteParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _stream(ctx, params.study_id, rec.id, None)
    rec.annotations = [a for a in rec.annotations if a.id != params.annotation_id]
    if stream:
        stream.annotations = [a for a in stream.annotations if a.id != params.annotation_id]
        ctx.studies.save_stream(params.study_id, stream)
    rec.decisions.append(
        HumanDecision(
            target_kind="annotation",
            target_id=params.annotation_id,
            action="reject",
            reason="annotations.delete",
        )
    )
    _persist_rec(ctx, params.study_id, rec)
    return {"deleted": params.annotation_id}

from __future__ import annotations

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import SyncMethod
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neuroflow.sync import apply_manual_offset, build_sync_group


class SyncCreateParams(BaseModel):
    study_id: str
    recording_id: str
    reference_stream_id: str | None = None
    method: SyncMethod = SyncMethod.SHARED_TRIGGERS
    manual_offsets: dict[str, float] = Field(default_factory=dict)


class SyncListParams(BaseModel):
    study_id: str
    recording_id: str | None = None


class SyncGetParams(BaseModel):
    study_id: str
    sync_group_id: str


class SyncOffsetParams(BaseModel):
    study_id: str
    sync_group_id: str
    stream_id: str
    offset_sec: float


@REGISTRY.register("sync.create", SyncCreateParams)
def sync_create(params: SyncCreateParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=params.recording_id)
    group = build_sync_group(
        recording_id=params.recording_id,
        streams=streams,
        reference_stream_id=params.reference_stream_id,
        method=params.method,
        manual_offsets=params.manual_offsets,
    )
    ctx.studies.save_sync_group(params.study_id, group)
    return {"sync_group": group.model_dump(mode="json")}


@REGISTRY.register("sync.list", SyncListParams)
def sync_list(params: SyncListParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    groups = ctx.studies.list_sync_groups(params.study_id, recording_id=params.recording_id)
    return {"sync_groups": [g.model_dump(mode="json") for g in groups]}


@REGISTRY.register("sync.get", SyncGetParams)
def sync_get(params: SyncGetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    group = ctx.studies.get_sync_group(params.study_id, params.sync_group_id)
    return group.model_dump(mode="json")


@REGISTRY.register("sync.set_offset", SyncOffsetParams)
def sync_set_offset(params: SyncOffsetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    group = ctx.studies.get_sync_group(params.study_id, params.sync_group_id)
    group = apply_manual_offset(group, params.stream_id, params.offset_sec)
    ctx.studies.save_sync_group(params.study_id, group)
    return {"sync_group": group.model_dump(mode="json")}

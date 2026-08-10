"""Phase 9 — channel / data management (stream-owned, reversible via decisions)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import ChannelStatus, ChannelType, HumanDecision, Modality
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY


class ChannelListParams(BaseModel):
    study_id: str
    recording_id: str
    stream_id: str | None = None


class ChannelUpdateParams(BaseModel):
    study_id: str
    recording_id: str
    stream_id: str | None = None
    channel_name: str
    new_name: str | None = None
    channel_type: str | None = None
    unit: str | None = None
    reference: str | None = None
    bad: bool | None = None


class ChannelReorderParams(BaseModel):
    study_id: str
    recording_id: str
    stream_id: str | None = None
    order: list[str] = Field(default_factory=list)  # channel names in desired order


class ChannelMontageParams(BaseModel):
    study_id: str
    recording_id: str
    stream_id: str | None = None
    montage: str = "standard_1020"


def _eeg_stream(ctx: AppContext, study_id: str, recording_id: str, stream_id: str | None):
    streams = ctx.studies.list_streams(study_id, recording_id=recording_id)
    if stream_id:
        return next(s for s in streams if s.id == stream_id)
    return next((s for s in streams if s.modality == Modality.EEG), streams[0] if streams else None)


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


@REGISTRY.register("channels.list", ChannelListParams)
def channels_list(params: ChannelListParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _eeg_stream(ctx, params.study_id, rec.id, params.stream_id)
    channels = stream.channels if stream else rec.channels
    return {
        "stream_id": stream.id if stream else None,
        "channels": [c.model_dump(mode="json") for c in channels],
    }


@REGISTRY.register("channels.update", ChannelUpdateParams)
def channels_update(params: ChannelUpdateParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _eeg_stream(ctx, params.study_id, rec.id, params.stream_id)
    if stream is None:
        raise KeyError("no stream for channel update")

    ch = next((c for c in stream.channels if c.name == params.channel_name), None)
    if ch is None:
        raise KeyError(f"channel not found: {params.channel_name}")

    old = ch.model_dump(mode="json")
    if params.new_name:
        ch.name = params.new_name
    if params.channel_type:
        ch.type = ChannelType(params.channel_type)
    if params.unit is not None:
        ch.unit = params.unit
    if params.reference is not None:
        ch.reference = params.reference
        stream.reference = params.reference
    if params.bad is not None:
        ch.status = ChannelStatus.BAD if params.bad else ChannelStatus.GOOD

    decision = HumanDecision(
        target_kind="channel",
        target_id=ch.id,
        action="mark_bad" if params.bad else "label",
        label=ch.name,
        reason="channels.update",
        metadata={"before": old, "after": ch.model_dump(mode="json")},
    )
    stream.decisions.append(decision)
    # mirror onto recording rollup
    for rch in rec.channels:
        if rch.id == ch.id or rch.name == params.channel_name:
            rch.name = ch.name
            rch.type = ch.type
            rch.unit = ch.unit
            rch.reference = ch.reference
            rch.status = ch.status
    rec.decisions.append(decision)
    ctx.studies.save_stream(params.study_id, stream)
    _persist_rec(ctx, params.study_id, rec)
    return {"channel": ch.model_dump(mode="json"), "decision": decision.model_dump(mode="json")}


@REGISTRY.register("channels.reorder", ChannelReorderParams)
def channels_reorder(params: ChannelReorderParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _eeg_stream(ctx, params.study_id, rec.id, params.stream_id)
    if stream is None:
        raise KeyError("no stream")
    by_name = {c.name: c for c in stream.channels}
    ordered = [by_name[n] for n in params.order if n in by_name]
    leftover = [c for c in stream.channels if c.name not in set(params.order)]
    stream.channels = ordered + leftover
    decision = HumanDecision(
        target_kind="stream",
        target_id=stream.id,
        action="label",
        reason="channels.reorder",
        metadata={"order": params.order},
    )
    stream.decisions.append(decision)
    rec.channels = list(stream.channels)
    rec.decisions.append(decision)
    ctx.studies.save_stream(params.study_id, stream)
    _persist_rec(ctx, params.study_id, rec)
    return {"channels": [c.model_dump(mode="json") for c in stream.channels]}


@REGISTRY.register("channels.apply_montage", ChannelMontageParams)
def channels_apply_montage(params: ChannelMontageParams, ctx: AppContext) -> dict:
    """Apply standard montage metadata to channel locations (does not rewrite samples)."""
    import mne

    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    stream = _eeg_stream(ctx, params.study_id, rec.id, params.stream_id)
    if stream is None:
        raise KeyError("no stream")
    montage = mne.channels.make_standard_montage(params.montage)
    pos = montage.get_positions()["ch_pos"]
    from suite_backend.domain.models import ChannelLocation

    updated = 0
    for ch in stream.channels:
        if ch.name in pos:
            xyz = pos[ch.name]
            ch.location = ChannelLocation(
                x=float(xyz[0]),
                y=float(xyz[1]),
                z=float(xyz[2]),
                coordinate_frame="head",
                source="standard",
            )
            ch.metadata = {**(ch.metadata or {}), "montage": params.montage}
            updated += 1
    decision = HumanDecision(
        target_kind="stream",
        target_id=stream.id,
        action="label",
        reason="channels.apply_montage",
        metadata={"montage": params.montage, "updated": updated},
    )
    stream.decisions.append(decision)
    rec.channels = list(stream.channels)
    rec.decisions.append(decision)
    ctx.studies.save_stream(params.study_id, stream)
    _persist_rec(ctx, params.study_id, rec)
    return {"montage": params.montage, "updated": updated, "channels": len(stream.channels)}

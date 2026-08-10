"""Apply / list / revert artifact suggestions (annotations + decisions only)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import (
    Annotation,
    ChannelStatus,
    HumanDecision,
    Modality,
)
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.algorithms.artifact_detection import detect_artifacts


class ArtifactDetectParams(BaseModel):
    study_id: str
    recording_id: str


class ArtifactApplyParams(BaseModel):
    study_id: str
    recording_id: str
    suggestion: dict = Field(default_factory=dict)
    reason: str | None = None


class ArtifactListParams(BaseModel):
    study_id: str
    recording_id: str


class ArtifactRevertParams(BaseModel):
    study_id: str
    recording_id: str
    annotation_id: str


def _primary_eeg_stream(ctx: AppContext, study_id: str, recording_id: str):
    streams = ctx.studies.list_streams(study_id, recording_id=recording_id)
    return next((s for s in streams if s.modality == Modality.EEG), streams[0] if streams else None)


@REGISTRY.register("artifacts.detect", ArtifactDetectParams)
def artifacts_detect(params: ArtifactDetectParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    return detect_artifacts(rec, streams=streams).model_dump(mode="json")


@REGISTRY.register("artifacts.apply", ArtifactApplyParams)
def artifacts_apply(params: ArtifactApplyParams, ctx: AppContext) -> dict:
    """Confirm a suggestion → Annotation + HumanDecision; never touches sample files."""
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    sug = dict(params.suggestion or {})
    kind = str(sug.get("kind") or "bad_segment")
    method = sug.get("method")
    threshold = sug.get("threshold")
    stream = _primary_eeg_stream(ctx, params.study_id, rec.id)
    stream_id = stream.id if stream else None

    if kind == "bad_channel":
        ch_name = str(sug.get("channel") or "")
        ann = Annotation(
            kind="channel",
            label="bad",
            channel_ids=[ch_name],
            stream_id=stream_id,
            metadata={
                "artifact": True,
                "method": method,
                "threshold": threshold,
                "value": sug.get("value"),
                "suggestion_id": sug.get("id"),
                "placeholder": sug.get("placeholder", True),
                "reason": params.reason or sug.get("reason"),
            },
        )
        # mark channel status on recording + stream
        for ch in rec.channels:
            if ch.name == ch_name:
                ch.status = ChannelStatus.BAD
        if stream:
            for ch in stream.channels:
                if ch.name == ch_name:
                    ch.status = ChannelStatus.BAD
    else:
        ann = Annotation(
            kind="continuous",
            label="artifact",
            start=float(sug["start"]) if sug.get("start") is not None else None,
            end=float(sug["end"]) if sug.get("end") is not None else None,
            stream_id=stream_id,
            metadata={
                "artifact": True,
                "method": method,
                "threshold": threshold,
                "value": sug.get("value"),
                "suggestion_id": sug.get("id"),
                "placeholder": sug.get("placeholder", True),
                "reason": params.reason or sug.get("reason"),
            },
        )

    decision = HumanDecision(
        target_kind="annotation",
        target_id=ann.id,
        action="accept",
        recommendation_id=str(sug.get("id")) if sug.get("id") else None,
        reason=params.reason or sug.get("reason"),
        label=ann.label,
        metadata={"kind": kind, "method": method},
    )
    rec.annotations.append(ann)
    rec.decisions.append(decision)
    if stream:
        stream.annotations.append(ann)
        stream.decisions.append(decision)
        ctx.studies.save_stream(params.study_id, stream)

    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for i, r in enumerate(run.recordings):
                    if r.id == rec.id:
                        run.recordings[i] = rec
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    return {
        "annotation": ann.model_dump(mode="json"),
        "decision": decision.model_dump(mode="json"),
        "note": "raw samples untouched; mask is annotation + decision only",
    }


@REGISTRY.register("artifacts.list", ArtifactListParams)
def artifacts_list(params: ArtifactListParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    masks = [
        a.model_dump(mode="json")
        for a in rec.annotations
        if (a.metadata or {}).get("artifact") or a.label in {"bad", "artifact"}
    ]
    return {"artifacts": masks, "count": len(masks)}


@REGISTRY.register("artifacts.revert", ArtifactRevertParams)
def artifacts_revert(params: ArtifactRevertParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    ann = next((a for a in rec.annotations if a.id == params.annotation_id), None)
    if ann is None:
        raise KeyError(f"annotation not found: {params.annotation_id}")

    # restore channel good if it was a bad_channel mask
    if ann.kind == "channel" and ann.channel_ids:
        names = set(ann.channel_ids)
        for ch in rec.channels:
            if ch.name in names:
                ch.status = ChannelStatus.GOOD
        stream = _primary_eeg_stream(ctx, params.study_id, rec.id)
        if stream:
            for ch in stream.channels:
                if ch.name in names:
                    ch.status = ChannelStatus.GOOD
            stream.annotations = [a for a in stream.annotations if a.id != ann.id]
            stream.decisions.append(
                HumanDecision(
                    target_kind="annotation",
                    target_id=ann.id,
                    action="reject",
                    reason="reverted artifact mask",
                    label=ann.label,
                )
            )
            ctx.studies.save_stream(params.study_id, stream)

    rec.annotations = [a for a in rec.annotations if a.id != ann.id]
    rec.decisions.append(
        HumanDecision(
            target_kind="annotation",
            target_id=ann.id,
            action="reject",
            reason="reverted artifact mask",
            label=ann.label,
        )
    )
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for i, r in enumerate(run.recordings):
                    if r.id == rec.id:
                        run.recordings[i] = rec
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    return {"reverted": params.annotation_id, "note": "annotation removed; raw untouched"}

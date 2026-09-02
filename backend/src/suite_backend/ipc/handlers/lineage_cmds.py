"""Lineage IPC commands.

Copyright 2026 NeuroTendrils
Proprietary — see LICENSE.

Two commands:

    lineage.chain           the ordered provenance chain for a recording
    lineage.signal_window   the signal as it was at a given step

``lineage.signal_window`` deliberately mirrors ``recordings.signal_window``
rather than adding a parameter to it. Keeping "show me now" and "show me then"
as separate commands means a bug in history replay can never return stale data
to the live view, and the allowlist makes the distinction visible.
"""

from __future__ import annotations

from pydantic import BaseModel

from suite_backend.app_context import AppContext
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neuroflow.lineage import build_chain, stream_at_artifact
from suite_backend.neuroflow.signal import signal_window


class LineageChainParams(BaseModel):
    study_id: str
    recording_id: str


class LineageWindowParams(BaseModel):
    study_id: str
    recording_id: str
    artifact_id: str
    start: float = 0.0
    duration: float = 5.0
    channel_names: list[str] | None = None
    max_points: int = 4000


@REGISTRY.register("lineage.chain", LineageChainParams)
def lineage_chain(params: LineageChainParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    recording = find_recording(study, params.recording_id)
    artifacts = ctx.studies.list_artifacts(params.study_id)
    steps = build_chain(recording, artifacts)
    return {
        "recording_id": recording.id,
        "steps": steps,
        # The head is the last replayable step; the UI anchors "Return to head"
        # here rather than assuming the last element.
        "head_index": max(
            (i for i, s in enumerate(steps) if s["replayable"]), default=-1
        ),
    }


@REGISTRY.register("lineage.signal_window", LineageWindowParams)
def lineage_signal_window(params: LineageWindowParams, ctx: AppContext) -> dict:
    """Window the signal as it existed at a specific step.

    Never mutates the study: ``stream_at_artifact`` returns a detached copy.
    """
    study = ctx.studies.get_study(params.study_id)
    recording = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=recording.id)

    artifacts = ctx.studies.list_artifacts(params.study_id)
    artifact = next((a for a in artifacts if a.id == params.artifact_id), None)
    if artifact is None:
        raise KeyError(f"artifact not found: {params.artifact_id}")
    if artifact.recording_id != recording.id:
        # A cross-recording artifact id would render one recording's signal
        # under another's lineage. Refuse rather than display something wrong.
        raise ValueError(
            f"artifact {params.artifact_id} does not belong to recording {recording.id}"
        )

    replay = stream_at_artifact(recording, streams, artifact)
    result = signal_window(
        recording,
        start=params.start,
        duration=params.duration,
        channel_names=params.channel_names,
        max_points=params.max_points,
        streams=[replay],
        stream_id=replay.id,
    )
    result["artifact_id"] = artifact.id
    result["operation"] = artifact.operation
    result["read_only"] = True
    return result

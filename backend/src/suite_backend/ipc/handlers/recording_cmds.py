from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Annotation, ChannelStatus, HumanDecision
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neuroflow.erp import compute_erp
from suite_backend.neuroflow.ica_ops import list_ica_components
from suite_backend.neuroflow.signal import signal_window
from suite_backend.scientific.io.importers import get_default_registry


class ImportInspectParams(BaseModel):
    path: str


class ColumnSpec(BaseModel):
    index: int
    name: str
    role: str = "eeg"  # eeg | stim | misc | ignore | time


class ImportRecordingParams(BaseModel):
    study_id: str
    subject_id: str
    session_id: str
    run_id: str
    path: str
    # Required for .txt/.csv/.tsv matrix imports (not embedded in file).
    sfreq: float | None = None
    # If true: rows=channels, cols=samples. Default: rows=samples, cols=channels.
    transpose: bool = False
    channel_names: list[str] | None = None
    include_columns: list[int] | None = None
    column_selection: list[ColumnSpec] | None = None
    # MNE standard montage name, e.g. standard_1020 / biosemi32
    montage: str | None = None


class RecordingIdParams(BaseModel):
    study_id: str
    recording_id: str


class SignalWindowParams(BaseModel):
    study_id: str
    recording_id: str
    start: float = 0.0
    duration: float = 5.0
    channel_names: list[str] | None = None
    max_points: int = 4000


class AnnotationCreateParams(BaseModel):
    study_id: str
    recording_id: str
    kind: str = "continuous"
    label: str
    start: float | None = None
    end: float | None = None
    channel_ids: list[str] = Field(default_factory=list)
    epoch_indices: list[int] = Field(default_factory=list)
    component_indices: list[int] = Field(default_factory=list)
    action: str = "label"


class ChannelBadParams(BaseModel):
    study_id: str
    recording_id: str
    channel_names: list[str]
    bad: bool = True


class ErpParams(BaseModel):
    study_id: str
    recording_id: str
    event_name: str | None = None
    tmin: float = -0.2
    tmax: float = 0.8


class IcaListParams(BaseModel):
    study_id: str
    recording_id: str
    n_components: int | None = 15


class IcaRejectParams(BaseModel):
    study_id: str
    recording_id: str
    component_indices: list[int]
    action: str = "reject"  # reject | keep


def _save_recording(ctx: AppContext, study_id: str, recording_id: str, mutate) -> dict:
    study = ctx.studies.get_study(study_id)
    recording = find_recording(study, recording_id)
    mutate(recording)
    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    return recording.model_dump(mode="json")


@REGISTRY.register("import.inspect", ImportInspectParams)
def import_inspect(params: ImportInspectParams, ctx: AppContext) -> dict:
    path = Path(params.path).expanduser().resolve()
    # Allow inspect outside workspace (sources live elsewhere); import copies metadata only.
    return get_default_registry().inspect(path)


@REGISTRY.register("import.recording", ImportRecordingParams)
def import_recording(params: ImportRecordingParams, ctx: AppContext) -> dict:
    path = Path(params.path).expanduser().resolve()
    registry = get_default_registry()
    importer = registry.find(path)
    if importer is None:
        raise ValueError(f"no importer for {path}")
    study = ctx.studies.get_study(params.study_id)
    artifact_dir = ctx.workspace.study_dir(study.id) / "artifacts" / "imports"
    kwargs: dict = {
        "subject_id": params.subject_id,
        "session_id": params.session_id,
        "run_id": params.run_id,
        "artifact_dir": artifact_dir,
    }
    if params.sfreq is not None:
        kwargs["sfreq"] = params.sfreq
    if params.transpose:
        kwargs["transpose"] = True
    if params.channel_names:
        kwargs["channel_names"] = params.channel_names
    if params.include_columns is not None:
        kwargs["include_columns"] = params.include_columns
    if params.column_selection is not None:
        kwargs["column_selection"] = [c.model_dump() for c in params.column_selection]
    if params.montage:
        kwargs["montage"] = params.montage
    recording, artifact, _raw = importer.import_recording(path, **kwargs)
    artifact.study_id = study.id
    placed = False
    for subject in study.subjects:
        if subject.id != params.subject_id:
            continue
        for session in subject.sessions:
            if session.id != params.session_id:
                continue
            for run in session.runs:
                if run.id != params.run_id:
                    continue
                run.recordings.append(recording)
                placed = True
    if not placed:
        raise KeyError("subject/session/run not found")
    ctx.studies.save_artifact(artifact)
    ctx.studies.save_study(study)
    return {
        "recording": recording.model_dump(mode="json"),
        "artifact": artifact.model_dump(mode="json"),
        "inspect": registry.inspect(path),
    }


@REGISTRY.register("recordings.get", RecordingIdParams)
def recordings_get(params: RecordingIdParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    return find_recording(study, params.recording_id).model_dump(mode="json")


@REGISTRY.register("recordings.inspect", RecordingIdParams)
def recordings_inspect(params: RecordingIdParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return {
        "recording_id": rec.id,
        "source_format": rec.source_format,
        "sampling_rate": rec.sampling_rate,
        "duration": rec.duration,
        "channel_count": rec.channel_count,
        "channels": [c.model_dump(mode="json") for c in rec.channels],
        "events": [e.model_dump(mode="json") for e in rec.events],
        "annotations": [a.model_dump(mode="json") for a in rec.annotations],
        "decisions": [d.model_dump(mode="json") for d in rec.decisions],
    }


@REGISTRY.register("recordings.signal_window", SignalWindowParams)
def recordings_signal_window(params: SignalWindowParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return signal_window(
        rec,
        start=params.start,
        duration=params.duration,
        channel_names=params.channel_names,
        max_points=params.max_points,
    )


@REGISTRY.register("annotations.create", AnnotationCreateParams)
def annotations_create(params: AnnotationCreateParams, ctx: AppContext) -> dict:
    def mutate(recording):
        ann = Annotation(
            kind=params.kind,
            label=params.label,
            start=params.start,
            end=params.end,
            channel_ids=params.channel_ids,
            epoch_indices=params.epoch_indices,
            component_indices=params.component_indices,
        )
        decision = HumanDecision(
            target_kind=params.kind,
            target_id=ann.id,
            action=params.action,
            label=params.label,
        )
        recording.annotations.append(ann)
        recording.decisions.append(decision)

    rec = _save_recording(ctx, params.study_id, params.recording_id, mutate)
    return {"recording": rec}


@REGISTRY.register("channels.set_bad", ChannelBadParams)
def channels_set_bad(params: ChannelBadParams, ctx: AppContext) -> dict:
    def mutate(recording):
        names = set(params.channel_names)
        for ch in recording.channels:
            if ch.name in names:
                ch.status = ChannelStatus.BAD if params.bad else ChannelStatus.GOOD
                recording.decisions.append(
                    HumanDecision(
                        target_kind="channel",
                        target_id=ch.id,
                        action="mark_bad" if params.bad else "mark_good",
                        label=ch.name,
                    )
                )

    return {"recording": _save_recording(ctx, params.study_id, params.recording_id, mutate)}


@REGISTRY.register("erp.compute", ErpParams)
def erp_compute(params: ErpParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return compute_erp(
        rec,
        event_name=params.event_name,
        tmin=params.tmin,
        tmax=params.tmax,
    )


@REGISTRY.register("ica.components.list", IcaListParams)
def ica_components_list(params: IcaListParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return list_ica_components(rec, n_components=params.n_components)


@REGISTRY.register("ica.component.set_rejection", IcaRejectParams)
def ica_set_rejection(params: IcaRejectParams, ctx: AppContext) -> dict:
    def mutate(recording):
        for idx in params.component_indices:
            recording.decisions.append(
                HumanDecision(
                    target_kind="ica_component",
                    target_id=str(idx),
                    action=params.action,
                    label=f"IC{idx}",
                )
            )
            recording.annotations.append(
                Annotation(
                    kind="ica_component",
                    label=params.action,
                    component_indices=[idx],
                )
            )

    return {"recording": _save_recording(ctx, params.study_id, params.recording_id, mutate)}

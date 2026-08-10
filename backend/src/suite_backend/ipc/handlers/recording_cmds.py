from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import (
    Annotation,
    ChannelStatus,
    DataStream,
    HumanDecision,
    Modality,
)
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neuroflow.clean_continuous import clean_continuous
from suite_backend.neuroflow.erp import compute_erp
from suite_backend.neuroflow.ica_ops import apply_ica_rejection, list_ica_components
from suite_backend.neuroflow.signal import signal_window
from suite_backend.neuroflow.working_fif import promote_working_fif
from suite_backend.scientific.io.importers import get_default_registry


def _primary_stream_from_recording(recording, artifact_paths: dict | None = None) -> DataStream:
    paths = dict(artifact_paths or {})
    fif = paths.get("fif") or next(
        (p for p in recording.source_files if str(p).endswith((".fif", ".fif.gz"))),
        None,
    )
    sample_paths = {"fif": str(fif)} if fif else {}
    return DataStream(
        recording_id=recording.id,
        subject_id=recording.subject_id,
        session_id=recording.session_id,
        run_id=recording.run_id,
        modality=Modality.EEG,
        name="eeg",
        source_files=list(recording.source_files),
        source_format=recording.source_format,
        sampling_rate=recording.sampling_rate,
        duration=recording.duration,
        n_samples=int(recording.duration * recording.sampling_rate)
        if recording.duration and recording.sampling_rate
        else None,
        channels=list(recording.channels),
        units="uV",
        events=list(recording.events),
        annotations=list(recording.annotations),
        decisions=list(recording.decisions),
        acquisition_metadata=dict(recording.acquisition_metadata),
        sample_paths=sample_paths,
        artifact_id=recording.artifact_id,
        provenance={"created_by": "import.recording", "normalized": False},
        reference=next((c.reference for c in recording.channels if c.reference), None),
    )


def _normalize_and_persist(ctx: AppContext, study_id: str, recording_id: str) -> dict:
    from suite_backend.scientific.io.canonical import normalize_recording

    study = ctx.studies.get_study(study_id)
    recording = find_recording(study, recording_id)
    streams = ctx.studies.list_streams(study_id, recording_id=recording_id)
    recording, streams, report = normalize_recording(recording, streams)
    # write back recording into study tree
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for i, rec in enumerate(run.recordings):
                    if rec.id == recording_id:
                        run.recordings[i] = recording
    ctx.studies.save_study(study)
    for stream in streams:
        ctx.studies.save_stream(study_id, stream)
    return report


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
    # Required for ambiguous formats (.txt/.csv/.tsv/.mat) — never silently guessed.
    sfreq: float | None = None
    # MAT: name of numeric array variable
    data_key: str | None = None
    # If true: rows=channels, cols=samples. Default: rows=samples, cols=channels.
    transpose: bool = False
    channel_names: list[str] | None = None
    include_columns: list[int] | None = None
    column_selection: list[ColumnSpec] | None = None
    # MNE standard montage name, e.g. standard_1020 / biosemi32
    montage: str | None = None


def _assert_import_config(inspect_info: dict, params: ImportRecordingParams) -> None:
    """Refuse ambiguous imports when required config is missing."""
    status = inspect_info.get("status")
    required = list(inspect_info.get("required_config") or [])
    if status not in {"needs_config", "ready", "ok"} and status not in (None,):
        if status in {"unreadable", "error"}:
            raise ValueError(
                f"cannot import: inspect status={status} "
                f"({inspect_info.get('error') or inspect_info.get('warnings')})"
            )
    missing: list[str] = []
    for key in required:
        if key == "sfreq" and params.sfreq is None:
            missing.append("sfreq")
        elif key == "data_key" and not params.data_key:
            missing.append("data_key")
    if missing:
        raise ValueError(
            "ambiguous format requires explicit config before import; missing: "
            + ", ".join(missing)
            + ". Call import.inspect and supply required_config fields."
        )


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
    stream_id: str | None = None


class NormalizeRecordingParams(BaseModel):
    study_id: str
    recording_id: str


class TimelineWindowParams(BaseModel):
    study_id: str
    recording_id: str
    start: float = 0.0
    duration: float = 5.0
    max_points: int = 2000
    stream_ids: list[str] | None = None
    sync_group_id: str | None = None


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
    erpimage_channel: str | None = None


class IcaListParams(BaseModel):
    study_id: str
    recording_id: str
    n_components: int | None = 15


class IcaRejectParams(BaseModel):
    study_id: str
    recording_id: str
    component_indices: list[int]
    action: str = "reject"  # reject | keep


class IcaApplyParams(BaseModel):
    study_id: str
    recording_id: str
    n_components: int | None = 15
    exclude: list[int] | None = None
    use_as_working: bool = True


class CleanContinuousParams(BaseModel):
    study_id: str
    recording_id: str
    z_thresh: float = 5.0
    use_as_working: bool = True


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
    inspect_info = registry.inspect(path)
    _assert_import_config(inspect_info, params)
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
    if params.data_key:
        kwargs["data_key"] = params.data_key
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
    stream = _primary_stream_from_recording(recording, artifact.paths)
    recording.stream_ids = [stream.id]
    if stream.id not in study.stream_ids:
        study.stream_ids.append(stream.id)
    artifact.stream_id = stream.id
    # Persist study (with recording) before stream sidecar so save_stream cannot clobber it.
    ctx.studies.save_study(study)
    ctx.studies.save_stream(study.id, stream)
    ctx.studies.save_artifact(artifact)
    norm = _normalize_and_persist(ctx, study.id, recording.id)
    study = ctx.studies.get_study(study.id)
    recording = find_recording(study, recording.id)
    stream = ctx.studies.get_stream(study.id, stream.id)
    return {
        "recording": recording.model_dump(mode="json"),
        "stream": stream.model_dump(mode="json"),
        "artifact": artifact.model_dump(mode="json"),
        "normalize": norm,
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
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    return {
        "recording_id": rec.id,
        "source_format": rec.source_format,
        "sampling_rate": rec.sampling_rate,
        "duration": rec.duration,
        "channel_count": rec.channel_count,
        "stream_ids": list(rec.stream_ids),
        "streams": [
            {
                "id": s.id,
                "modality": s.modality.value,
                "sfreq": s.sampling_rate,
                "n_channels": len(s.channels),
                "n_samples": s.n_samples,
                "units": s.units,
                "sample_paths": s.sample_paths,
                "normalized": bool((s.provenance or {}).get("normalized")),
            }
            for s in streams
        ],
        "channels": [c.model_dump(mode="json") for c in rec.channels],
        "events": [e.model_dump(mode="json") for e in rec.events],
        "annotations": [a.model_dump(mode="json") for a in rec.annotations],
        "decisions": [d.model_dump(mode="json") for d in rec.decisions],
        "preprocessing_state": rec.preprocessing_state,
    }


@REGISTRY.register("recordings.normalize", NormalizeRecordingParams)
def recordings_normalize(params: NormalizeRecordingParams, ctx: AppContext) -> dict:
    report = _normalize_and_persist(ctx, params.study_id, params.recording_id)
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return {
        "recording": rec.model_dump(mode="json"),
        "normalize": report,
    }


@REGISTRY.register("recordings.signal_window", SignalWindowParams)
def recordings_signal_window(params: SignalWindowParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    return signal_window(
        rec,
        start=params.start,
        duration=params.duration,
        channel_names=params.channel_names,
        max_points=params.max_points,
        streams=streams,
        stream_id=params.stream_id,
    )


@REGISTRY.register("recordings.timeline", TimelineWindowParams)
def recordings_timeline(params: TimelineWindowParams, ctx: AppContext) -> dict:
    from suite_backend.neuroflow.timeline import timeline_window

    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    sync_group = None
    if params.sync_group_id:
        sync_group = ctx.studies.get_sync_group(params.study_id, params.sync_group_id)
    else:
        groups = ctx.studies.list_sync_groups(params.study_id, recording_id=rec.id)
        sync_group = groups[-1] if groups else None
    return timeline_window(
        rec,
        streams,
        start=params.start,
        duration=params.duration,
        max_points=params.max_points,
        sync_group=sync_group,
        stream_ids=params.stream_ids,
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
    from suite_backend.domain.models import Modality

    names = set(params.channel_names)

    def mutate(recording):
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

    rec = _save_recording(ctx, params.study_id, params.recording_id, mutate)
    # keep stream-owned channels in sync (visualizer source of truth)
    streams = ctx.studies.list_streams(params.study_id, recording_id=params.recording_id)
    for stream in streams:
        if stream.modality != Modality.EEG and not any(c.name in names for c in stream.channels):
            continue
        dirty = False
        for ch in stream.channels:
            if ch.name in names:
                ch.status = ChannelStatus.BAD if params.bad else ChannelStatus.GOOD
                dirty = True
        if dirty:
            stream.decisions.append(
                HumanDecision(
                    target_kind="channel",
                    target_id=",".join(sorted(names)),
                    action="mark_bad" if params.bad else "mark_good",
                    reason="channels.set_bad",
                )
            )
            ctx.studies.save_stream(params.study_id, stream)
    return {"recording": rec}


@REGISTRY.register("erp.compute", ErpParams)
def erp_compute(params: ErpParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    return compute_erp(
        rec,
        event_name=params.event_name,
        tmin=params.tmin,
        tmax=params.tmax,
        streams=streams,
        erpimage_channel=params.erpimage_channel,
    )


@REGISTRY.register("ica.components.list", IcaListParams)
def ica_components_list(params: IcaListParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    return list_ica_components(rec, n_components=params.n_components, streams=streams)


@REGISTRY.register("ica.component.set_rejection", IcaRejectParams)
def ica_set_rejection(params: IcaRejectParams, ctx: AppContext) -> dict:
    def mutate(recording):
        wanted = set(params.component_indices)
        # replace prior IC annotations so keep/reject isn't ambiguous in the list
        recording.annotations = [
            a
            for a in recording.annotations
            if not (
                a.kind == "ica_component"
                and wanted.intersection(int(i) for i in a.component_indices)
            )
        ]
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


@REGISTRY.register("ica.apply", IcaApplyParams)
def ica_apply(params: IcaApplyParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    art_dir = ctx.workspace.study_dir(params.study_id) / "artifacts" / "ica"
    result = apply_ica_rejection(
        rec,
        study_id=params.study_id,
        artifact_dir=art_dir,
        streams=streams,
        n_components=params.n_components,
        exclude=params.exclude,
    )
    artifact = result["artifact"]
    ctx.studies.save_artifact(artifact)
    promoted: list[str] = []
    if params.use_as_working:
        promoted = promote_working_fif(
            ctx,
            study_id=params.study_id,
            recording_id=rec.id,
            fif_path=result["fif"],
        )

    def mutate(recording):
        recording.decisions.append(
            HumanDecision(
                target_kind="ica_apply",
                target_id=artifact.id,
                action="apply",
                reason=f"exclude={result['excluded']}",
                label="ica.apply",
            )
        )
        recording.preprocessing_state = {
            **(recording.preprocessing_state or {}),
            "ica_applied_artifact_id": artifact.id,
            "ica_excluded": result["excluded"],
        }

    rec_dump = _save_recording(ctx, params.study_id, params.recording_id, mutate)
    return {
        "artifact": artifact.model_dump(mode="json"),
        "excluded": result["excluded"],
        "promoted_streams": promoted,
        "recording": rec_dump,
        "note": "ICA removed components → new FIF; source import untouched",
    }


@REGISTRY.register("neuroflow.clean_continuous", CleanContinuousParams)
def neuroflow_clean_continuous(params: CleanContinuousParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    art_dir = ctx.workspace.study_dir(params.study_id) / "artifacts" / "clean"
    result = clean_continuous(
        rec,
        study_id=params.study_id,
        artifact_dir=art_dir,
        streams=streams,
        z_thresh=params.z_thresh,
    )
    artifact = result["artifact"]
    ctx.studies.save_artifact(artifact)
    promoted: list[str] = []
    if params.use_as_working:
        promoted = promote_working_fif(
            ctx,
            study_id=params.study_id,
            recording_id=rec.id,
            fif_path=artifact.paths["fif"],
        )

    def mutate(recording):
        recording.decisions.append(
            HumanDecision(
                target_kind="clean_continuous",
                target_id=artifact.id,
                action="apply",
                reason=f"z_thresh={params.z_thresh}; bad_spans={result['n_bad_spans']}",
                label="neuroflow.clean_continuous",
            )
        )
        recording.preprocessing_state = {
            **(recording.preprocessing_state or {}),
            "clean_artifact_id": artifact.id,
        }

    rec_dump = _save_recording(ctx, params.study_id, params.recording_id, mutate)
    return {
        "artifact": artifact.model_dump(mode="json"),
        "n_bad_spans": result["n_bad_spans"],
        "bad_spans": result["bad_spans"],
        "duration_before": result["duration_before"],
        "duration_after": result["duration_after"],
        "promoted_streams": promoted,
        "recording": rec_dump,
        "warning": result["warning"],
    }

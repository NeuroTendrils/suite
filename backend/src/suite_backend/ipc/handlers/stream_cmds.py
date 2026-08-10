from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Recording
from suite_backend.domain.queries import find_recording, find_recording_in_subject, find_run
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.io.external_stream import (
    import_external_stream,
    inspect_external_source,
)


class StreamInspectParams(BaseModel):
    path: str


class ColumnSpec(BaseModel):
    index: int
    name: str
    role: str = "eeg"


class ImportStreamParams(BaseModel):
    study_id: str
    subject_id: str
    session_id: str
    run_id: str
    path: str
    modality: str
    # Attach to existing recording, or omit to create a new recording shell.
    recording_id: str | None = None
    sfreq: float | None = None
    units: str | None = None
    name: str | None = None
    data_key: str | None = None
    transpose: bool = False
    channel_names: list[str] | None = None
    include_columns: list[int] | None = None
    column_selection: list[ColumnSpec] | None = None
    timestamp_column: int | None = None


@REGISTRY.register("import.stream.inspect", StreamInspectParams)
def import_stream_inspect(params: StreamInspectParams, ctx: AppContext) -> dict:
    del ctx
    path = Path(params.path).expanduser().resolve()
    return inspect_external_source(path)


@REGISTRY.register("import.stream", ImportStreamParams)
def import_stream(params: ImportStreamParams, ctx: AppContext) -> dict:
    path = Path(params.path).expanduser().resolve()
    inspect_info = inspect_external_source(path)
    if inspect_info.get("status") == "unreadable":
        raise ValueError(f"cannot import stream: {inspect_info.get('error')}")

    required = set(inspect_info.get("required_config") or [])
    missing = []
    if "modality" in required and not params.modality:
        missing.append("modality")
    if "sfreq" in required and params.sfreq is None and params.timestamp_column is None:
        # timestamp via column role is allowed inside column_selection
        has_time = any(c.role == "time" for c in (params.column_selection or []))
        if not has_time:
            missing.append("sfreq|timestamp_column")
    if "data_key" in required and not params.data_key:
        missing.append("data_key")
    if missing:
        raise ValueError(
            "external stream requires explicit config; missing: " + ", ".join(missing)
        )

    study = ctx.studies.get_study(params.study_id)
    # Subject-scoped path to avoid cross-subject attachment
    find_run(study, params.subject_id, params.session_id, params.run_id)

    created_recording = False
    if params.recording_id:
        recording = find_recording_in_subject(study, params.subject_id, params.recording_id)
    else:
        recording = Recording(
            subject_id=params.subject_id,
            session_id=params.session_id,
            run_id=params.run_id,
            name=params.name or params.modality,
            source_files=[str(path)],
            source_format="external_stream",
        )
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
        created_recording = True

    sample_dir = ctx.workspace.study_dir(study.id) / "streams" / "samples"
    stream, artifact = import_external_stream(
        path,
        study_id=study.id,
        recording_id=recording.id,
        subject_id=params.subject_id,
        session_id=params.session_id,
        run_id=params.run_id,
        modality=params.modality,
        sfreq=params.sfreq,
        units=params.units,
        name=params.name,
        data_key=params.data_key,
        transpose=params.transpose,
        channel_names=params.channel_names,
        include_columns=params.include_columns,
        column_selection=[c.model_dump() for c in params.column_selection]
        if params.column_selection
        else None,
        timestamp_column=params.timestamp_column,
        sample_dir=sample_dir,
    )

    if stream.id not in recording.stream_ids:
        recording.stream_ids.append(stream.id)
    if stream.id not in study.stream_ids:
        study.stream_ids.append(stream.id)

    # If this is the first/only stream on a new recording, roll up convenience fields
    if created_recording or not recording.sampling_rate:
        recording.sampling_rate = stream.sampling_rate
        recording.duration = stream.duration
        recording.channel_count = len(stream.channels)
        recording.channels = list(stream.channels)
        recording.source_format = stream.source_format

    study.updated_at = datetime.now(timezone.utc)
    ctx.studies.save_study(study)
    ctx.studies.save_stream(study.id, stream)
    ctx.studies.save_artifact(artifact)

    return {
        "recording": find_recording(study, recording.id).model_dump(mode="json"),
        "stream": stream.model_dump(mode="json"),
        "artifact": artifact.model_dump(mode="json"),
        "created_recording": created_recording,
        "inspect": inspect_info,
    }

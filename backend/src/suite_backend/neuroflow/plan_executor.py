from __future__ import annotations

import hashlib
import json
from typing import Any

from suite_backend.domain.models import DatasetArtifact, ProcessingPlan, Recording
from suite_backend.storage.local import LocalStudyRepository


SUPPORTED_OPS = {
    "resample",
    "filter_bandpass",
    "filter_notch",
    "rereference",
    "baseline",
    "epoch",
    "mark_bad_channels",
    "interpolate_bads",
}


def execute_plan(
    *,
    study_id: str,
    plan: ProcessingPlan,
    recording: Recording,
    repo: LocalStudyRepository,
    raw: Any | None = None,
) -> list[DatasetArtifact]:
    """
    Execute a ProcessingPlan step-by-step, writing immutable artifacts.

    Uses MNE when raw is provided / loadable from source. Never mutates source files.
    """
    import mne

    if raw is None:
        from suite_backend.scientific.io.canonical import load_primary_eeg_raw

        streams = repo.list_streams(study_id, recording_id=recording.id)
        raw = load_primary_eeg_raw(recording, streams)
    else:
        raw = raw.copy().load_data()

    artifacts: list[DatasetArtifact] = []
    parent_id = recording.artifact_id
    current = raw

    art_root = repo.workspace.study_dir(study_id) / "artifacts"

    for step in plan.steps:
        if step.operation not in SUPPORTED_OPS:
            raise ValueError(f"unsupported operation: {step.operation}")
        current = _apply_step(current, step.operation, step.parameters)
        out_path = art_root / f"{step.id}.fif"
        if hasattr(current, "save"):
            current.save(out_path, overwrite=True)
        else:
            # Epochs
            current.save(out_path, overwrite=True)

        payload = {
            "operation": step.operation,
            "parameters": step.parameters,
            "plan_id": plan.id,
            "plan_version": plan.version,
            "step_id": step.id,
        }
        checksum = hashlib.sha256(out_path.read_bytes()).hexdigest()
        artifact = DatasetArtifact(
            type=step.output_type,
            parent_id=parent_id,
            source=recording.id,
            operation=step.operation,
            parameters=payload,
            checksum=checksum,
            paths={"fif": str(out_path)},
            recording_id=recording.id,
            study_id=study_id,
        )
        repo.save_artifact(artifact)
        artifacts.append(artifact)
        parent_id = artifact.id
        # also write sidecar meta
        (art_root / f"{artifact.id}.meta.json").write_text(
            json.dumps(artifact.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    return artifacts


def _apply_step(raw: Any, operation: str, params: dict[str, Any]) -> Any:
    if operation == "resample":
        return raw.copy().resample(params["sfreq"])
    if operation == "filter_bandpass":
        return raw.copy().filter(
            l_freq=params.get("l_freq"),
            h_freq=params.get("h_freq"),
            verbose=False,
        )
    if operation == "filter_notch":
        freqs = params.get("freqs", [60.0])
        return raw.copy().notch_filter(freqs=freqs, verbose=False)
    if operation == "rereference":
        ref = params.get("ref", "average")
        inst = raw.copy()
        if ref == "average":
            inst.set_eeg_reference("average", verbose=False)
        else:
            inst.set_eeg_reference(ref, verbose=False)
        return inst
    if operation == "baseline":
        # meaningful on epochs; on raw this is a no-op marker step
        return raw
    if operation == "mark_bad_channels":
        inst = raw.copy()
        bads = list(params.get("bads") or [])
        inst.info["bads"] = sorted(set(list(inst.info.get("bads") or []) + bads))
        return inst
    if operation == "interpolate_bads":
        inst = raw.copy()
        if inst.info.get("bads"):
            inst.interpolate_bads(reset_bads=False, verbose=False)
        return inst
    if operation == "epoch":
        import mne

        event_id = params.get("event_id")
        tmin = float(params.get("tmin", -0.2))
        tmax = float(params.get("tmax", 0.8))
        events, found_id = mne.events_from_annotations(raw, verbose=False)
        if event_id is None:
            event_id = found_id
        elif isinstance(event_id, str):
            event_id = {event_id: found_id[event_id]} if event_id in found_id else found_id
        epochs = mne.Epochs(
            raw,
            events,
            event_id=event_id,
            tmin=tmin,
            tmax=tmax,
            baseline=tuple(params.get("baseline", (None, 0))),
            preload=True,
            verbose=False,
        )
        return epochs
    raise ValueError(operation)

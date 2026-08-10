"""Phase 12 — EpochSet / Trial creation and listing."""

from __future__ import annotations

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import EpochSet, Modality, Trial
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.io.canonical import load_primary_eeg_raw
from suite_backend.scientific.io.stim_events import extract_events_from_raw


class EpochCreateParams(BaseModel):
    study_id: str
    recording_id: str
    name: str = "epochs"
    tmin: float = -0.2
    tmax: float = 0.8
    baseline: list[float | None] = Field(default_factory=lambda: [None, 0.0])
    event_names: list[str] | None = None
    save_fif: bool = True


class EpochListParams(BaseModel):
    study_id: str
    recording_id: str | None = None


class EpochGetParams(BaseModel):
    study_id: str
    epochset_id: str


@REGISTRY.register("epochs.create", EpochCreateParams)
def epochs_create(params: EpochCreateParams, ctx: AppContext) -> dict:
    import mne

    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    raw = load_primary_eeg_raw(rec, streams)

    # Ensure annotations exist for MNE epoching
    if len(raw.annotations) == 0:
        evs = extract_events_from_raw(raw)
        if not evs and rec.events:
            evs = list(rec.events)
        if evs:
            from suite_backend.scientific.io.stim_events import apply_events_as_annotations

            apply_events_as_annotations(raw, evs)

    events, event_id = mne.events_from_annotations(raw, verbose=False)
    if events is None or len(events) == 0:
        raise ValueError("no events/annotations available to build epochs")

    if params.event_names:
        available = list(event_id.keys())
        event_id = {k: v for k, v in event_id.items() if k in set(params.event_names)}
        if not event_id:
            raise ValueError(f"none of event_names {params.event_names} found in {available}")

    baseline = params.baseline
    if len(baseline) != 2:
        baseline = [None, 0.0]
    epochs = mne.Epochs(
        raw,
        events,
        event_id=event_id,
        tmin=params.tmin,
        tmax=params.tmax,
        baseline=(baseline[0], baseline[1]),
        preload=True,
        verbose=False,
    )

    eeg_streams = [s for s in streams if s.modality == Modality.EEG]
    stream_ids = [s.id for s in eeg_streams] or [s.id for s in streams]
    modalities = sorted({s.modality.value for s in streams}) or ["eeg"]

    id_to_name = {v: k for k, v in event_id.items()}
    trials: list[Trial] = []
    sfreq = float(raw.info["sfreq"])
    for i in range(len(epochs)):
        ev_row = epochs.events[i]
        sample = int(ev_row[0])
        code = int(ev_row[2])
        ename = id_to_name.get(code, str(code))
        trials.append(
            Trial(
                index=i,
                subject_id=rec.subject_id,
                session_id=rec.session_id,
                run_id=rec.run_id,
                recording_id=rec.id,
                condition=ename,
                event_name=ename,
                onset=sample / sfreq,
                tmin=params.tmin,
                tmax=params.tmax,
                stream_ids=stream_ids,
                modalities=modalities,
                rejected=False,
            )
        )

    artifact_paths: dict[str, str] = {}

    epset = EpochSet(
        study_id=params.study_id,
        recording_id=rec.id,
        name=params.name,
        tmin=params.tmin,
        tmax=params.tmax,
        baseline=list(baseline),
        event_names=list(event_id.keys()),
        trials=trials,
        stream_ids=stream_ids,
        provenance={
            "n_epochs": len(trials),
            "sfreq": sfreq,
            "event_id": event_id,
            "source": "epochs.create",
        },
    )
    if params.save_fif:
        fif_path = ctx.workspace.study_dir(params.study_id) / "epochs" / f"{epset.id}_epo.fif"
        epochs.save(fif_path, overwrite=True, verbose=False)
        artifact_paths["fif"] = str(fif_path)
        epset.artifact_paths = artifact_paths

    ctx.studies.save_epochset(params.study_id, epset)
    return {
        "epochset": epset.model_dump(mode="json"),
        "n_trials": len(trials),
    }


@REGISTRY.register("epochs.list", EpochListParams)
def epochs_list(params: EpochListParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    sets = ctx.studies.list_epochsets(params.study_id, recording_id=params.recording_id)
    return {
        "epochsets": [
            {
                "id": e.id,
                "name": e.name,
                "recording_id": e.recording_id,
                "n_trials": len(e.trials),
                "event_names": e.event_names,
                "tmin": e.tmin,
                "tmax": e.tmax,
            }
            for e in sets
        ]
    }


@REGISTRY.register("epochs.get", EpochGetParams)
def epochs_get(params: EpochGetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    return ctx.studies.get_epochset(params.study_id, params.epochset_id).model_dump(mode="json")

"""Phase 12 — EpochSet / Trial creation and listing."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import EpochSet, HumanDecision, Modality, Trial
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


class EpochRejectParams(BaseModel):
    study_id: str
    epochset_id: str
    trial_indices: list[int]
    rejected: bool = True
    rewrite_fif: bool = True


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
        artifact_paths["fif_original"] = str(fif_path)
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
                "created_at": e.created_at.isoformat(),
            }
            for e in sets
        ]
    }


@REGISTRY.register("epochs.get", EpochGetParams)
def epochs_get(params: EpochGetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    return ctx.studies.get_epochset(params.study_id, params.epochset_id).model_dump(mode="json")


@REGISTRY.register("epochs.reject", EpochRejectParams)
def epochs_reject(params: EpochRejectParams, ctx: AppContext) -> dict:
    """Mark trials rejected (by eye). Optionally drop from saved epochs FIF."""
    ctx.studies.get_study(params.study_id)
    epset = ctx.studies.get_epochset(params.study_id, params.epochset_id)
    wanted = set(params.trial_indices)
    n_changed = 0
    for t in epset.trials:
        if t.index in wanted:
            t.rejected = params.rejected
            n_changed += 1
    epset.provenance = dict(epset.provenance or {})
    epset.provenance["reject_ops"] = list(epset.provenance.get("reject_ops") or []) + [
        {
            "trial_indices": list(params.trial_indices),
            "rejected": params.rejected,
        }
    ]

    fif_note = None
    paths = dict(epset.artifact_paths or {})
    orig = paths.get("fif_original") or paths.get("fif")
    if params.rewrite_fif and orig and Path(orig).exists():
        import mne

        if "fif_original" not in paths:
            paths["fif_original"] = orig
        epochs = mne.read_epochs(orig, preload=True, verbose=False)
        keep_mask = [not t.rejected for t in sorted(epset.trials, key=lambda x: x.index)]
        if len(keep_mask) == len(epochs) and any(keep_mask):
            cleaned = epochs[keep_mask]
            out = Path(orig).with_name(Path(orig).stem.replace("_epo", "") + "_clean_epo.fif")
            if out == Path(orig):
                out = Path(orig).with_name(Path(orig).stem + "_clean.fif")
            cleaned.save(out, overwrite=True, verbose=False)
            paths["fif"] = str(out)
            epset.artifact_paths = paths
            fif_note = f"wrote clean FIF with {len(cleaned)} / {len(epochs)} trials"
        elif not any(keep_mask):
            fif_note = "all trials rejected — original FIF kept; no clean FIF written"
        else:
            fif_note = "FIF length mismatch — metadata updated only"

    ctx.studies.save_epochset(params.study_id, epset)
    try:
        study = ctx.studies.get_study(params.study_id)
        rec = find_recording(study, epset.recording_id)
        rec.decisions.append(
            HumanDecision(
                target_kind="epoch",
                target_id=epset.id,
                action="reject" if params.rejected else "keep",
                reason=f"trials={params.trial_indices}",
                label="epochs.reject",
            )
        )
        for subject in study.subjects:
            for session in subject.sessions:
                for run in session.runs:
                    for i, r in enumerate(run.recordings):
                        if r.id == rec.id:
                            run.recordings[i] = rec
        ctx.studies.save_study(study)
    except KeyError:
        pass

    return {
        "epochset": epset.model_dump(mode="json"),
        "n_changed": n_changed,
        "n_rejected": sum(1 for t in epset.trials if t.rejected),
        "fif_note": fif_note,
    }

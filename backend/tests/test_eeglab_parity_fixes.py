"""ICA apply, continuous clean, epoch reject, ERP image."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.epoch_cmds import (
    EpochCreateParams,
    EpochRejectParams,
    epochs_create,
    epochs_reject,
)
from suite_backend.ipc.handlers.recording_cmds import (
    CleanContinuousParams,
    ErpParams,
    IcaApplyParams,
    IcaRejectParams,
    ImportRecordingParams,
    erp_compute,
    ica_apply,
    ica_set_rejection,
    import_recording,
    neuroflow_clean_continuous,
)
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add


def _seed_recording(tmp_path: Path, *, with_events: bool = True):
    mne = pytest.importorskip("mne")
    pytest.importorskip("sklearn")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Parity")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz", "Pz", "Oz"], 100.0, ch_types="eeg")
    data = np.random.randn(4, 2000) * 1e-6
    # inject a loud burst for clean_continuous
    data[:, 800:900] += 50e-6
    raw = mne.io.RawArray(data, info, verbose=False)
    if with_events:
        raw.set_annotations(
            mne.Annotations(
                onset=[1.0, 3.0, 5.0, 7.0, 9.0],
                duration=[0] * 5,
                description=["square"] * 5,
            )
        )
    fif = tmp_path / "parity.fif"
    raw.save(fif, overwrite=True, verbose=False)
    eeg = import_recording(
        ImportRecordingParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            path=str(fif),
        ),
        ctx,
    )
    return ctx, study.id, eeg["recording"]["id"]


def test_ica_reject_then_keep_unrejects(tmp_path: Path) -> None:
    from suite_backend.ipc.handlers.recording_cmds import IcaListParams, ica_components_list

    ctx, study_id, rid = _seed_recording(tmp_path)
    ica_set_rejection(
        IcaRejectParams(
            study_id=study_id,
            recording_id=rid,
            component_indices=[0],
            action="reject",
        ),
        ctx,
    )
    listed = ica_components_list(
        IcaListParams(study_id=study_id, recording_id=rid, n_components=4),
        ctx,
    )
    assert listed["components"][0]["rejected"] is True
    ica_set_rejection(
        IcaRejectParams(
            study_id=study_id,
            recording_id=rid,
            component_indices=[0],
            action="keep",
        ),
        ctx,
    )
    listed2 = ica_components_list(
        IcaListParams(study_id=study_id, recording_id=rid, n_components=4),
        ctx,
    )
    assert listed2["components"][0]["rejected"] is False


def test_ica_apply_writes_artifact_and_promotes(tmp_path: Path) -> None:
    ctx, study_id, rid = _seed_recording(tmp_path)
    ica_set_rejection(
        IcaRejectParams(
            study_id=study_id,
            recording_id=rid,
            component_indices=[0],
            action="reject",
        ),
        ctx,
    )
    out = ica_apply(
        IcaApplyParams(study_id=study_id, recording_id=rid, n_components=4, use_as_working=True),
        ctx,
    )
    assert out["excluded"] == [0]
    fif = Path(out["artifact"]["paths"]["fif"])
    assert fif.exists()
    assert out["promoted_streams"]
    streams = ctx.studies.list_streams(study_id, recording_id=rid)
    assert any(s.sample_paths.get("fif") == str(fif) for s in streams)


def test_clean_continuous_shortens(tmp_path: Path) -> None:
    ctx, study_id, rid = _seed_recording(tmp_path, with_events=False)
    out = neuroflow_clean_continuous(
        CleanContinuousParams(study_id=study_id, recording_id=rid, z_thresh=3.0),
        ctx,
    )
    assert out["n_bad_spans"] >= 1
    assert out["duration_after"] < out["duration_before"]
    assert Path(out["artifact"]["paths"]["fif"]).exists()


def test_epochs_reject_and_erpimage(tmp_path: Path) -> None:
    ctx, study_id, rid = _seed_recording(tmp_path)
    created = epochs_create(
        EpochCreateParams(
            study_id=study_id,
            recording_id=rid,
            tmin=-0.1,
            tmax=0.3,
            name="squares",
        ),
        ctx,
    )
    eid = created["epochset"]["id"]
    rejected = epochs_reject(
        EpochRejectParams(
            study_id=study_id,
            epochset_id=eid,
            trial_indices=[0, 2],
            rejected=True,
        ),
        ctx,
    )
    assert rejected["n_changed"] == 2
    assert rejected["n_rejected"] == 2
    clean = Path(rejected["epochset"]["artifact_paths"]["fif"])
    orig = Path(rejected["epochset"]["artifact_paths"]["fif_original"])
    assert orig.exists()
    assert clean.exists()
    assert clean != orig

    restored = epochs_reject(
        EpochRejectParams(
            study_id=study_id,
            epochset_id=eid,
            trial_indices=[0],
            rejected=False,
        ),
        ctx,
    )
    assert restored["n_rejected"] == 1
    assert any(t["index"] == 0 and not t["rejected"] for t in restored["epochset"]["trials"])

    erp = erp_compute(
        ErpParams(study_id=study_id, recording_id=rid, erpimage_channel="Cz"),
        ctx,
    )
    assert erp["status"] == "ok"
    assert erp["erpimage"] is not None
    assert erp["erpimage"]["channel"] == "Cz"
    assert len(erp["erpimage"]["trials"]) >= 1

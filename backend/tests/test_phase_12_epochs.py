from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.epoch_cmds import (
    EpochCreateParams,
    EpochListParams,
    epochs_create,
    epochs_list,
)
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add


def test_epochs_create_from_annotations(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Epo")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(2, 1000) * 1e-6, info, verbose=False)
    raw.set_annotations(
        mne.Annotations(onset=[1.0, 3.0, 5.0], duration=[0, 0, 0], description=["square"] * 3)
    )
    fif = tmp_path / "e.fif"
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
    rid = eeg["recording"]["id"]
    created = epochs_create(
        EpochCreateParams(
            study_id=study.id,
            recording_id=rid,
            tmin=-0.1,
            tmax=0.3,
            name="squares",
        ),
        ctx,
    )
    assert created["n_trials"] >= 1
    assert created["epochset"]["trials"][0]["subject_id"]
    assert created["epochset"]["trials"][0]["event_name"] == "square"
    listed = epochs_list(EpochListParams(study_id=study.id, recording_id=rid), ctx)
    assert len(listed["epochsets"]) >= 1

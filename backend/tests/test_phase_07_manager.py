from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import (
    StudyGetParams,
    SubjectAddParams,
    studies_manager,
    subjects_add,
)


def test_studies_manager_payload(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Mgr")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(1, 100), info, verbose=False)
    fif = tmp_path / "eeg_raw.fif"
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
    mgr = studies_manager(StudyGetParams(study_id=study.id), ctx)
    assert mgr["study_id"] == study.id
    assert mgr["subjects"][0]["label"] == "S001"
    rec = mgr["subjects"][0]["sessions"][0]["runs"][0]["recordings"][0]
    assert rec["id"] == eeg["recording"]["id"]
    assert "eeg" in rec["modalities"]
    assert isinstance(rec["streams"], list)
    assert rec["streams"][0]["modality"] == "eeg"

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.neuroflow_cmds import (
    PlanDefaultParams,
    PlanExecuteParams,
    plans_default,
    plans_execute,
)
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add
from suite_backend.neuroflow.default_plan import default_preprocessing_plan


def test_default_plan_placeholder_and_execute(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Plan")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz"], 200.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(2, 1000) * 1e-6, info, verbose=False)
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
    plan_body = plans_default(PlanDefaultParams(study_id=study.id, persist=True), ctx)
    assert plan_body["placeholder"] is True
    assert "PLACEHOLDER" in (plan_body["plan"]["notes"] or "").upper() or plan_body[
        "warning"
    ]
    plan_id = plan_body["plan"]["id"]
    # execute only first step-equivalent: create a tiny custom plan of one notch via default steps
    # default has bandpass+notch+reref — should write artifacts
    out = plans_execute(
        PlanExecuteParams(study_id=study.id, plan_id=plan_id, recording_id=rid),
        ctx,
    )
    assert len(out["artifacts"]) == len(default_preprocessing_plan().steps)
    assert Path(out["artifacts"][0]["paths"]["fif"]).exists()

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.stream_cmds import ImportStreamParams, import_stream
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add
from suite_backend.ipc.handlers.sync_cmds import SyncCreateParams, sync_create
from suite_backend.ipc.handlers.validate_cmds import (
    ValidateRecordingParams,
    ValidateStudyParams,
    validate_recording_cmd,
    validate_study_cmd,
)
from suite_backend.domain.models import SyncMethod


def test_validate_recording_ok_and_warns_without_sync(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Val")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(2, 200), info, verbose=False)
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
    gyro = tmp_path / "g.csv"
    gyro.write_text("x,y\n1,2\n3,4\n", encoding="utf-8")
    import_stream(
        ImportStreamParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            recording_id=eeg["recording"]["id"],
            path=str(gyro),
            modality="gyroscope",
            sfreq=50.0,
        ),
        ctx,
    )
    report = validate_recording_cmd(
        ValidateRecordingParams(study_id=study.id, recording_id=eeg["recording"]["id"]),
        ctx,
    )
    assert report["ok"] is True
    codes = {w["code"] for w in report["warnings"]}
    assert "no_sync_group" in codes or "mixed_sfreq" in codes

    sync_create(
        SyncCreateParams(
            study_id=study.id,
            recording_id=eeg["recording"]["id"],
            method=SyncMethod.MANUAL_OFFSET,
        ),
        ctx,
    )
    report2 = validate_recording_cmd(
        ValidateRecordingParams(study_id=study.id, recording_id=eeg["recording"]["id"]),
        ctx,
    )
    codes2 = {w["code"] for w in report2["warnings"]}
    assert "no_sync_group" not in codes2

    study_report = validate_study_cmd(ValidateStudyParams(study_id=study.id), ctx)
    assert study_report["scope"] == "study"
    assert study_report["ok"] is True

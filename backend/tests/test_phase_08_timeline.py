from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.recording_cmds import (
    ImportRecordingParams,
    TimelineWindowParams,
    import_recording,
    recordings_timeline,
)
from suite_backend.ipc.handlers.stream_cmds import ImportStreamParams, import_stream
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add
from suite_backend.ipc.handlers.sync_cmds import SyncCreateParams, sync_create
from suite_backend.domain.models import SyncMethod


def test_timeline_returns_tracks(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("TL")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(1, 300), info, verbose=False)
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
    gyro.write_text("x\n" + "\n".join(str(i) for i in range(30)), encoding="utf-8")
    import_stream(
        ImportStreamParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            recording_id=eeg["recording"]["id"],
            path=str(gyro),
            modality="gyroscope",
            sfreq=10.0,
        ),
        ctx,
    )
    sync_create(
        SyncCreateParams(
            study_id=study.id,
            recording_id=eeg["recording"]["id"],
            method=SyncMethod.MANUAL_OFFSET,
            manual_offsets={},
        ),
        ctx,
    )
    tl = recordings_timeline(
        TimelineWindowParams(
            study_id=study.id,
            recording_id=eeg["recording"]["id"],
            start=0.0,
            duration=2.0,
            max_points=64,
        ),
        ctx,
    )
    assert tl["recording_id"] == eeg["recording"]["id"]
    assert len(tl["streams"]) >= 2
    modalities = {t["modality"] for t in tl["streams"]}
    assert "eeg" in modalities
    assert "gyroscope" in modalities
    for track in tl["streams"]:
        assert "times" in track
        assert "data" in track
        assert len(track["times"]) == len(track["data"][0]) if track["data"] else True

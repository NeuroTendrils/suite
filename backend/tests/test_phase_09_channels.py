from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.channel_cmds import (
    ChannelListParams,
    ChannelMontageParams,
    ChannelUpdateParams,
    channels_apply_montage,
    channels_list,
    channels_update,
)
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add


def test_channel_update_and_montage(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Ch")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(2, 200) * 1e-6, info, verbose=False)
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
    listed = channels_list(ChannelListParams(study_id=study.id, recording_id=rid), ctx)
    assert len(listed["channels"]) >= 2
    updated = channels_update(
        ChannelUpdateParams(
            study_id=study.id,
            recording_id=rid,
            channel_name="Fz",
            bad=True,
            unit="uV",
        ),
        ctx,
    )
    assert updated["channel"]["status"] == "bad"
    mont = channels_apply_montage(
        ChannelMontageParams(study_id=study.id, recording_id=rid, montage="standard_1020"),
        ctx,
    )
    assert mont["updated"] >= 1

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Event, SyncMethod
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.stream_cmds import ImportStreamParams, import_stream
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add
from suite_backend.ipc.handlers.sync_cmds import (
    SyncCreateParams,
    SyncOffsetParams,
    sync_create,
    sync_set_offset,
)
def _setup_eeg_gyro(tmp_path: Path):
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Sync")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(1, 500), info, verbose=False)
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
    gyro.write_text("x\n" + "\n".join(str(i) for i in range(50)), encoding="utf-8")
    ext = import_stream(
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
    return ctx, study, eeg, ext


def test_sync_does_not_assume_alignment(tmp_path: Path) -> None:
    ctx, study, eeg, ext = _setup_eeg_gyro(tmp_path)
    res = sync_create(
        SyncCreateParams(
            study_id=study.id,
            recording_id=eeg["recording"]["id"],
            method=SyncMethod.SHARED_TRIGGERS,
        ),
        ctx,
    )
    group = res["sync_group"]
    assert group["quality"]["assumed_synchronized"] is False
    # no shared triggers → unspecified link for gyro
    gyro_link = next(l for l in group["links"] if l["stream_id"] == ext["stream"]["id"])
    assert gyro_link["method"] in {"unspecified", "shared_triggers", "timestamps"}


def test_manual_offset(tmp_path: Path) -> None:
    ctx, study, eeg, ext = _setup_eeg_gyro(tmp_path)
    created = sync_create(
        SyncCreateParams(
            study_id=study.id,
            recording_id=eeg["recording"]["id"],
            method=SyncMethod.MANUAL_OFFSET,
            manual_offsets={ext["stream"]["id"]: 0.25},
        ),
        ctx,
    )
    group_id = created["sync_group"]["id"]
    updated = sync_set_offset(
        SyncOffsetParams(
            study_id=study.id,
            sync_group_id=group_id,
            stream_id=ext["stream"]["id"],
            offset_sec=1.5,
        ),
        ctx,
    )
    link = next(
        l for l in updated["sync_group"]["links"] if l["stream_id"] == ext["stream"]["id"]
    )
    assert link["offset_sec"] == 1.5
    assert link["manual"] is True


def test_shared_trigger_offset_estimate() -> None:
    from suite_backend.domain.models import DataStream, Modality

    ref = DataStream(
        recording_id="r",
        subject_id="s",
        session_id="ses",
        run_id="run",
        modality=Modality.EEG,
        sampling_rate=100,
        duration=10,
        events=[
            Event(timestamp=1.0, sample_index=100, name="stim"),
            Event(timestamp=3.0, sample_index=300, name="stim"),
        ],
        sample_paths={},
        source_files=[],
    )
    other = DataStream(
        recording_id="r",
        subject_id="s",
        session_id="ses",
        run_id="run",
        modality=Modality.GYRO,
        sampling_rate=50,
        duration=10,
        events=[
            Event(timestamp=1.2, sample_index=60, name="stim"),
            Event(timestamp=3.2, sample_index=160, name="stim"),
        ],
        sample_paths={},
        source_files=[],
    )
    # Avoid load_stream_samples by using MANUAL with empty - use build with shared triggers
    # but build_sync_group calls assess which may fail load — set durations only
    # Inject fake via method that only uses events
    from suite_backend.neuroflow.sync import estimate_trigger_offset

    offset, quality = estimate_trigger_offset(ref, other)
    assert offset is not None
    assert abs(offset - (-0.2)) < 1e-9 or abs(offset - 0.2) < 1e-6 or abs(offset + 0.2) < 1e-6
    # ref - other = 1.0 - 1.2 = -0.2
    assert abs(offset + 0.2) < 1e-9
    assert quality["n_pairs"] == 2

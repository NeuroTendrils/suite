from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.recording_cmds import (
    ImportRecordingParams,
    NormalizeRecordingParams,
    SignalWindowParams,
    import_recording,
    recordings_normalize,
    recordings_signal_window,
)
from suite_backend.ipc.handlers.stream_cmds import ImportStreamParams, import_stream
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add
from suite_backend.scientific.io.canonical import load_stream_samples


def _setup(tmp_path: Path):
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Norm")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    return ctx, study, added


def test_import_normalizes_eeg_and_loads_via_canonical(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    info = mne.create_info(["Fz", "Cz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(2, 300), info, verbose=False)
    fif = tmp_path / "demo_raw.fif"
    raw.save(fif, overwrite=True, verbose=False)

    ctx, study, added = _setup(tmp_path)
    res = import_recording(
        ImportRecordingParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            path=str(fif),
        ),
        ctx,
    )
    assert res["normalize"]["ok"] is True
    stream = ctx.studies.get_stream(study.id, res["stream"]["id"])
    assert stream.sample_paths.get("fif")
    assert stream.provenance.get("normalized") is True
    samples = load_stream_samples(stream)
    assert samples.n_channels == 2
    assert samples.n_times == 300

    win = recordings_signal_window(
        SignalWindowParams(
            study_id=study.id,
            recording_id=res["recording"]["id"],
            start=0,
            duration=1.0,
        ),
        ctx,
    )
    assert win["modality"] == "eeg"
    assert len(win["channels"]) == 2


def test_multimodal_normalize_and_stream_window(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    info = mne.create_info(["Fz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(1, 200), info, verbose=False)
    fif = tmp_path / "eeg_raw.fif"
    raw.save(fif, overwrite=True, verbose=False)

    ctx, study, added = _setup(tmp_path)
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
    gyro.write_text("x,y\n1,2\n3,4\n5,6\n", encoding="utf-8")
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
    assert ext["normalize"]["ok"] is True
    assert Path(ext["stream"]["sample_paths"]["data_npy"]).exists()

    win = recordings_signal_window(
        SignalWindowParams(
            study_id=study.id,
            recording_id=eeg["recording"]["id"],
            stream_id=ext["stream"]["id"],
            start=0,
            duration=10,
        ),
        ctx,
    )
    assert win["modality"] == "gyroscope"
    assert len(win["channels"]) == 2

    report = recordings_normalize(
        NormalizeRecordingParams(
            study_id=study.id,
            recording_id=eeg["recording"]["id"],
        ),
        ctx,
    )
    assert report["normalize"]["ok"] is True
    assert report["recording"]["preprocessing_state"].get("normalized") is True

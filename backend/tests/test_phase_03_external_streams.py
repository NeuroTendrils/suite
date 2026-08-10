from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.stream_cmds import (
    ImportStreamParams,
    StreamInspectParams,
    import_stream,
    import_stream_inspect,
)
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add
from suite_backend.scientific.io.external_stream import inspect_external_source


def _ctx_study(tmp_path: Path):
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("MultiModal")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    return ctx, study, added


def test_external_inspect_needs_modality_and_sfreq(tmp_path: Path) -> None:
    path = tmp_path / "subject_gyro.csv"
    path.write_text("t,x,y,z\n0,0.1,0.2,0.3\n0.01,0.1,0.2,0.4\n", encoding="utf-8")
    info = inspect_external_source(path)
    assert info["status"] == "needs_config"
    assert "modality" in info["required_config"]
    assert "sfreq" in info["required_config"]
    assert info["suggested_modality"] == "gyroscope"
    assert info["self_describing"] is False


def test_import_stream_refuses_without_modality(tmp_path: Path) -> None:
    path = tmp_path / "accel.txt"
    path.write_text("1 2 3\n4 5 6\n", encoding="utf-8")
    ctx, study, added = _ctx_study(tmp_path)
    with pytest.raises(ValueError, match="modality|sfreq"):
        import_stream(
            ImportStreamParams(
                study_id=study.id,
                subject_id=added["subject"]["id"],
                session_id=added["session_id"],
                run_id=added["run_id"],
                path=str(path),
                modality="",
                sfreq=50.0,
            ),
            ctx,
        )


def test_attach_gyro_stream_to_eeg_recording(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    # EEG recording
    info = mne.create_info(["Fz", "Cz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(2, 200), info, verbose=False)
    fif = tmp_path / "eeg_raw.fif"
    raw.save(fif, overwrite=True, verbose=False)

    ctx, study, added = _ctx_study(tmp_path)
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
    rec_id = eeg["recording"]["id"]

    gyro = tmp_path / "imu_gyro.csv"
    rows = ["gx,gy,gz"]
    for i in range(50):
        rows.append(f"{0.01 * i},{0.02 * i},{0.03 * i}")
    gyro.write_text("\n".join(rows), encoding="utf-8")

    inspected = import_stream_inspect(StreamInspectParams(path=str(gyro)), ctx)
    assert inspected["suggested_modality"] == "gyroscope"

    res = import_stream(
        ImportStreamParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            recording_id=rec_id,
            path=str(gyro),
            modality="gyroscope",
            sfreq=50.0,
            units="deg/s",
        ),
        ctx,
    )
    assert res["created_recording"] is False
    assert res["stream"]["modality"] == "gyroscope"
    assert res["stream"]["sampling_rate"] == 50.0
    assert len(res["stream"]["channels"]) == 3
    assert res["stream"]["units"] == "deg/s"
    assert Path(res["stream"]["sample_paths"]["data_npy"]).exists()

    streams = ctx.studies.list_streams(study.id, recording_id=rec_id)
    mods = {s.modality.value for s in streams}
    assert "eeg" in mods
    assert "gyroscope" in mods
    assert len(streams) == 2


def test_create_recording_for_ecg_only(tmp_path: Path) -> None:
    path = tmp_path / "ecg_lead.csv"
    path.write_text("v\n0.1\n0.2\n0.15\n0.3\n", encoding="utf-8")
    ctx, study, added = _ctx_study(tmp_path)
    res = import_stream(
        ImportStreamParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            path=str(path),
            modality="ecg",
            sfreq=256.0,
        ),
        ctx,
    )
    assert res["created_recording"] is True
    assert res["recording"]["source_format"] in {"csv", "external_stream"}
    assert res["stream"]["modality"] == "ecg"
    assert res["stream"]["n_samples"] == 4

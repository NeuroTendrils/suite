from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.recording_cmds import (
    ImportRecordingParams,
    import_recording,
)
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add
from suite_backend.scientific.io.importers import get_default_registry
from suite_backend.scientific.io.mat_import import inspect_mat, import_mat_recording


def _study_with_subject(ctx: AppContext):
    study = ctx.studies.create_study("ImportTest")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    return study, added


def test_fif_inspect_ready_and_import(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    sfreq = 100.0
    info = mne.create_info(["Fz", "Cz"], sfreq, ch_types="eeg")
    data = np.random.randn(2, 200)
    raw = mne.io.RawArray(data, info, verbose=False)
    fif = tmp_path / "demo_raw.fif"
    raw.save(fif, overwrite=True, verbose=False)

    reg = get_default_registry()
    info_i = reg.inspect(fif)
    assert info_i["status"] == "ready"
    assert info_i["self_describing"] is True
    assert info_i["required_config"] == []

    ctx = AppContext(tmp_path / "ws")
    study, added = _study_with_subject(ctx)
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
    assert res["recording"]["source_format"] == "fif"
    assert res["stream"]["modality"] == "eeg"
    assert res["recording"]["channel_count"] == 2
    assert Path(res["artifact"]["paths"]["fif"]).exists()


def test_text_import_refuses_without_sfreq(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_text("1 2 3\n4 5 6\n", encoding="utf-8")
    reg = get_default_registry()
    info = reg.inspect(path)
    assert info["status"] == "needs_config"
    assert "sfreq" in info["required_config"]
    assert info["self_describing"] is False

    ctx = AppContext(tmp_path / "ws")
    study, added = _study_with_subject(ctx)
    with pytest.raises(ValueError, match="sfreq"):
        import_recording(
            ImportRecordingParams(
                study_id=study.id,
                subject_id=added["subject"]["id"],
                session_id=added["session_id"],
                run_id=added["run_id"],
                path=str(path),
            ),
            ctx,
        )


def test_text_import_with_sfreq(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    rng = np.random.default_rng(0)
    data = rng.normal(size=(100, 3))
    body = "\n".join(" ".join(f"{v:.5f}" for v in row) for row in data)
    path.write_text("Fz Cz Pz\n" + body, encoding="utf-8")

    ctx = AppContext(tmp_path / "ws")
    study, added = _study_with_subject(ctx)
    res = import_recording(
        ImportRecordingParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            path=str(path),
            sfreq=250.0,
        ),
        ctx,
    )
    assert res["recording"]["sampling_rate"] == 250.0
    assert res["recording"]["channel_count"] == 3


def test_mat_inspect_and_import(tmp_path: Path) -> None:
    pytest.importorskip("scipy")
    from scipy.io import savemat

    path = tmp_path / "blob.mat"
    eeg = np.random.randn(150, 4)
    savemat(str(path), {"eeg_data": eeg, "misc": np.array([1, 2, 3])})

    info = inspect_mat(path)
    assert info["status"] == "needs_config"
    assert "data_key" in info["required_config"]
    assert "sfreq" in info["required_config"]
    keys = {c["key"] for c in info["candidates"]}
    assert "eeg_data" in keys

    ctx = AppContext(tmp_path / "ws")
    study, added = _study_with_subject(ctx)
    with pytest.raises(ValueError, match="data_key|sfreq"):
        import_recording(
            ImportRecordingParams(
                study_id=study.id,
                subject_id=added["subject"]["id"],
                session_id=added["session_id"],
                run_id=added["run_id"],
                path=str(path),
            ),
            ctx,
        )

    recording, artifact, raw = import_mat_recording(
        path,
        subject_id=added["subject"]["id"],
        session_id=added["session_id"],
        run_id=added["run_id"],
        data_key="eeg_data",
        sfreq=128.0,
        artifact_dir=tmp_path / "arts",
    )
    assert recording.channel_count == 4
    assert recording.sampling_rate == 128.0
    assert raw.n_times == 150
    assert Path(artifact.paths["fif"]).exists()

    res = import_recording(
        ImportRecordingParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            path=str(path),
            data_key="eeg_data",
            sfreq=128.0,
        ),
        ctx,
    )
    assert res["stream"]["modality"] == "eeg"
    assert res["recording"]["source_format"] == "mat"

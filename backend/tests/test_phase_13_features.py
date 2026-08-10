from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.feature_cmds import (
    FeatureExtractParams,
    FeatureListParams,
    features_extract,
    features_list,
)
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add


def test_band_power_and_psd_extract(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Feat")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz"], 200.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(2, 2000) * 1e-6, info, verbose=False)
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
    bp = features_extract(
        FeatureExtractParams(study_id=study.id, recording_id=rid, kind="band_power"),
        ctx,
    )
    assert bp["n_features"] > 0
    assert bp["featureset"]["kind"] == "band_power"
    assert bp["featureset"]["export_paths"].get("csv")
    psd = features_extract(
        FeatureExtractParams(study_id=study.id, recording_id=rid, kind="psd"),
        ctx,
    )
    assert psd["featureset"]["kind"] == "psd"
    listed = features_list(FeatureListParams(study_id=study.id, recording_id=rid), ctx)
    assert len(listed["featuresets"]) >= 2

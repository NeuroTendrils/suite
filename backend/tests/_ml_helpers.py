"""Shared helpers for ML pipeline smoke tests (phases 14–24)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.epoch_cmds import EpochCreateParams, epochs_create
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add


def seed_two_class_recording(tmp_path: Path):
    mne = pytest.importorskip("mne")
    pytest.importorskip("sklearn")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("ML")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz"], 100.0, ch_types="eeg")
    data = np.random.randn(2, 3000) * 1e-6
    raw = mne.io.RawArray(data, info, verbose=False)
    raw.set_annotations(
        mne.Annotations(
            onset=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            duration=[0] * 8,
            description=["A", "B", "A", "B", "A", "B", "A", "B"],
        )
    )
    fif = tmp_path / "ml_raw.fif"
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
    ep = epochs_create(
        EpochCreateParams(
            study_id=study.id,
            recording_id=rid,
            tmin=-0.1,
            tmax=0.3,
            name="ab",
        ),
        ctx,
    )
    return ctx, study.id, rid, ep["epochset"]["id"]

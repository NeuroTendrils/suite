from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.artifact_cmds import (
    ArtifactApplyParams,
    ArtifactDetectParams,
    ArtifactListParams,
    ArtifactRevertParams,
    artifacts_apply,
    artifacts_detect,
    artifacts_list,
    artifacts_revert,
)
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add


def _import_eeg(tmp_path: Path):
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Art")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz", "Cz", "Pz"], 100.0, ch_types="eeg")
    data = np.random.randn(3, 500) * 1e-6
    data[0] *= 50  # make Fz a high-amplitude outlier
    raw = mne.io.RawArray(data, info, verbose=False)
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
    return ctx, study, eeg


def test_detect_and_apply_revert(tmp_path: Path) -> None:
    ctx, study, eeg = _import_eeg(tmp_path)
    rid = eeg["recording"]["id"]
    report = artifacts_detect(ArtifactDetectParams(study_id=study.id, recording_id=rid), ctx)
    assert "recommendations" in report
    assert any("placeholder" in w.lower() or "heuristic" in w.lower() for w in report["warnings"])

    # apply a synthetic bad segment (does not require detector hit)
    applied = artifacts_apply(
        ArtifactApplyParams(
            study_id=study.id,
            recording_id=rid,
            suggestion={
                "id": "sug_test",
                "kind": "bad_segment",
                "start": 0.5,
                "end": 1.0,
                "method": "manual",
                "reason": "test mask",
            },
        ),
        ctx,
    )
    ann_id = applied["annotation"]["id"]
    listed = artifacts_list(ArtifactListParams(study_id=study.id, recording_id=rid), ctx)
    assert listed["count"] >= 1
    # raw path still present
    rec = ctx.studies.get_study(study.id)
    from suite_backend.domain.queries import find_recording

    recording = find_recording(rec, rid)
    assert recording.source_files

    reverted = artifacts_revert(
        ArtifactRevertParams(study_id=study.id, recording_id=rid, annotation_id=ann_id),
        ctx,
    )
    assert reverted["reverted"] == ann_id
    listed2 = artifacts_list(ArtifactListParams(study_id=study.id, recording_id=rid), ctx)
    assert all(a["id"] != ann_id for a in listed2["artifacts"])

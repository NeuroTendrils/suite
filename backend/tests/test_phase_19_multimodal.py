from __future__ import annotations

from pathlib import Path

import numpy as np

from suite_backend.ipc.handlers.dataset_cmds import DatasetBuildParams, datasets_build
from suite_backend.ipc.handlers.stream_cmds import ImportStreamParams, import_stream
from tests._ml_helpers import seed_two_class_recording


def test_multimodal_dataset(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    study = ctx.studies.get_study(study_id)
    sub = study.subjects[0]
    ses = sub.sessions[0]
    run = ses.runs[0]

    gyro = tmp_path / "gyro.csv"
    rows = ["gx,gy"]
    for i in range(3000):
        rows.append(f"{np.sin(i / 10):.6f},{np.cos(i / 10):.6f}")
    gyro.write_text("\n".join(rows), encoding="utf-8")
    import_stream(
        ImportStreamParams(
            study_id=study_id,
            subject_id=sub.id,
            session_id=ses.id,
            run_id=run.id,
            recording_id=rid,
            path=str(gyro),
            modality="gyroscope",
            sfreq=100.0,
        ),
        ctx,
    )
    out = datasets_build(
        DatasetBuildParams(
            study_id=study_id,
            recording_id=rid,
            epochset_id=eid,
            source="multimodal",
            name="eeg_gyro",
        ),
        ctx,
    )["dataset"]
    assert out["source"] == "multimodal"
    assert "eeg" in out["modalities"]
    assert "gyroscope" in out["modalities"]
    assert out["n_features"] > 10

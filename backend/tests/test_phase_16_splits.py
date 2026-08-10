from __future__ import annotations

from pathlib import Path

from suite_backend.ipc.handlers.dataset_cmds import (
    DatasetBuildParams,
    SplitCreateParams,
    datasets_build,
    splits_create,
)
from suite_backend.neurostudio.generalization import detect_leakage
from tests._ml_helpers import seed_two_class_recording


def test_split_and_leakage(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    ds = datasets_build(
        DatasetBuildParams(
            study_id=study_id, recording_id=rid, epochset_id=eid, source="epochs"
        ),
        ctx,
    )["dataset"]
    split = splits_create(
        SplitCreateParams(
            study_id=study_id,
            dataset_id=ds["id"],
            method="stratified_trial",
            test_frac=0.25,
            seed=1,
        ),
        ctx,
    )["split"]
    assert split["train_indices"]
    assert split["test_indices"]
    assert "leakage_check" in split
    leak = detect_leakage(
        {"train_subjects": ["a"], "val_subjects": [], "test_subjects": ["a"]}
    )
    assert leak["ok"] is False

from __future__ import annotations

from pathlib import Path

from suite_backend.ipc.handlers.dataset_cmds import (
    DatasetBuildParams,
    DatasetListParams,
    datasets_build,
    datasets_list,
)
from tests._ml_helpers import seed_two_class_recording


def test_build_dataset_from_epochs(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    out = datasets_build(
        DatasetBuildParams(
            study_id=study_id,
            recording_id=rid,
            epochset_id=eid,
            source="epochs",
            name="ab_bp",
        ),
        ctx,
    )
    ds = out["dataset"]
    assert ds["n_samples"] >= 4
    assert ds["n_features"] > 0
    assert set(ds["label_names"]) == {"A", "B"}
    assert Path(ds["paths"]["X"]).exists()
    listed = datasets_list(DatasetListParams(study_id=study_id), ctx)
    assert any(d["id"] == ds["id"] for d in listed["datasets"])

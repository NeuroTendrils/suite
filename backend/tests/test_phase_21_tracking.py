from __future__ import annotations

from pathlib import Path

from suite_backend.ipc.handlers.dataset_cmds import DatasetBuildParams, datasets_build
from suite_backend.ipc.handlers.neurostudio_cmds import (
    ExperimentCreateParams,
    ExperimentIdParams,
    ExperimentListParams,
    experiments_create,
    experiments_get,
    experiments_list,
)
from tests._ml_helpers import seed_two_class_recording


def test_experiment_list_get(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    ds = datasets_build(
        DatasetBuildParams(
            study_id=study_id, recording_id=rid, epochset_id=eid, source="epochs"
        ),
        ctx,
    )["dataset"]
    created = experiments_create(
        ExperimentCreateParams(
            study_id=study_id,
            input_artifact_id=ds["id"],
            template_id="eegnet",
        ),
        ctx,
    )["experiment"]
    listed = experiments_list(ExperimentListParams(study_id=study_id), ctx)
    assert any(e["id"] == created["id"] for e in listed["experiments"])
    got = experiments_get(
        ExperimentIdParams(study_id=study_id, experiment_id=created["id"]),
        ctx,
    )
    assert got["id"] == created["id"]
    assert got["template_id"] == "eegnet"

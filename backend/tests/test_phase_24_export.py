from __future__ import annotations

from pathlib import Path
import zipfile

from suite_backend.ipc.handlers.dataset_cmds import (
    DatasetBuildParams,
    SplitCreateParams,
    datasets_build,
    splits_create,
)
from suite_backend.ipc.handlers.neurostudio_cmds import (
    ExperimentCreateParams,
    ExportStudyParams,
    TrainParams,
    experiments_create,
    model_export,
    study_export,
    train_start,
)
from tests._ml_helpers import seed_two_class_recording


def test_export_study_and_model(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    ds = datasets_build(
        DatasetBuildParams(
            study_id=study_id, recording_id=rid, epochset_id=eid, source="epochs"
        ),
        ctx,
    )["dataset"]
    split = splits_create(
        SplitCreateParams(
            study_id=study_id, dataset_id=ds["id"], method="stratified_trial", seed=0
        ),
        ctx,
    )["split"]
    exp = experiments_create(
        ExperimentCreateParams(
            study_id=study_id,
            input_artifact_id=ds["id"],
            template_id="eegnet",
            split_definition={"split_id": split["id"]},
        ),
        ctx,
    )["experiment"]
    train_start(TrainParams(study_id=study_id, experiment_id=exp["id"]), ctx)

    study_pkg = study_export(
        ExportStudyParams(study_id=study_id, include_samples=False),
        ctx,
    )
    assert study_pkg["status"] == "ok"
    assert zipfile.is_zipfile(study_pkg["path"])

    model_pkg = model_export(
        TrainParams(study_id=study_id, experiment_id=exp["id"]),
        ctx,
    )
    assert model_pkg["status"] == "ok"
    assert zipfile.is_zipfile(model_pkg["path"])

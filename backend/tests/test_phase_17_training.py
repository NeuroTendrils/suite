from __future__ import annotations

from pathlib import Path

from suite_backend.ipc.handlers.dataset_cmds import (
    DatasetBuildParams,
    SplitCreateParams,
    datasets_build,
    splits_create,
)
from suite_backend.ipc.handlers.neurostudio_cmds import (
    ExperimentCreateParams,
    RecommendTemplatesParams,
    TrainParams,
    experiments_create,
    templates_recommend,
    train_start,
)
from tests._ml_helpers import seed_two_class_recording


def test_recommend_baselines_and_train_legacy_sklearn(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    rec = templates_recommend(RecommendTemplatesParams(study_id=study_id), ctx)
    assert rec["recommendations"][0]["template_id"] == "research_auto"

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
            random_seed=0,
        ),
        ctx,
    )["experiment"]
    out = train_start(TrainParams(study_id=study_id, experiment_id=exp["id"]), ctx)
    assert out["status"] == "ok", out
    assert Path(out["model"]["paths"]["joblib"]).exists()

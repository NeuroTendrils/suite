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
    InferParams,
    TrainParams,
    experiments_create,
    infer_run,
    train_start,
)
from tests._ml_helpers import seed_two_class_recording


def test_infer_labels(tmp_path: Path) -> None:
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
    out = infer_run(InferParams(study_id=study_id, experiment_id=exp["id"]), ctx)
    assert out["status"] == "ok"
    assert len(out["labels"]) == ds["n_samples"]


def _trained(tmp_path: Path):
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    ds = datasets_build(
        DatasetBuildParams(study_id=study_id, recording_id=rid, epochset_id=eid, source="epochs"),
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
    return ctx, study_id, ds, split, exp


def test_infer_on_held_out_split_reports_confidence_and_truth(tmp_path: Path) -> None:
    ctx, study_id, _ds, split, exp = _trained(tmp_path)
    out = infer_run(InferParams(study_id=study_id, experiment_id=exp["id"], split="test"), ctx)
    assert out["status"] == "ok"
    assert out["indices"] == split["test_indices"]
    n = len(split["test_indices"])
    assert len(out["labels"]) == len(out["true_labels"]) == len(out["confidence"]) == n
    assert all(0.0 <= c <= 1.0 for c in out["confidence"])
    for row, conf in zip(out["proba"], out["confidence"]):
        assert abs(sum(row) - 1.0) < 1e-6 and conf == max(row)
    assert set(out["labels"]) <= set(out["classes"])
    assert out["runs_locally"] is True


def test_trained_model_is_labelled_with_what_was_actually_trained(tmp_path: Path) -> None:
    ctx, study_id, _ds, _split, exp = _trained(tmp_path)
    out = infer_run(InferParams(study_id=study_id, experiment_id=exp["id"], split="test"), ctx)
    assert out["template_id"] == "sklearn_logreg"
    model = ctx.studies.get_model(study_id, out["model_id"])
    assert model.metadata["requested_template"] == "eegnet"


def test_infer_rejects_unknown_split(tmp_path: Path) -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InferParams(study_id="s", experiment_id="e", split="holdout")

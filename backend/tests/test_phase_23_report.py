from __future__ import annotations

from pathlib import Path

from suite_backend.ipc.handlers.dataset_cmds import DatasetBuildParams, datasets_build
from suite_backend.ipc.handlers.neurostudio_cmds import (
    ExperimentCreateParams,
    ReportParams,
    experiments_create,
    report_build,
)
from tests._ml_helpers import seed_two_class_recording


def test_study_and_experiment_reports(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    ds = datasets_build(
        DatasetBuildParams(
            study_id=study_id, recording_id=rid, epochset_id=eid, source="epochs"
        ),
        ctx,
    )["dataset"]
    exp = experiments_create(
        ExperimentCreateParams(
            study_id=study_id, input_artifact_id=ds["id"], template_id="eegnet"
        ),
        ctx,
    )["experiment"]
    summary = report_build(ReportParams(study_id=study_id), ctx)
    assert summary["status"] == "ok"
    assert Path(summary["path"]).exists()
    report = report_build(
        ReportParams(study_id=study_id, experiment_id=exp["id"]),
        ctx,
    )
    assert report["status"] == "ok"
    assert "Experiment report" in report["markdown"]
    assert Path(report["path"]).exists()

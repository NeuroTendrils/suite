from __future__ import annotations

from pathlib import Path

from suite_backend.ipc.handlers.analysis_cmds import (
    AnalysisListParams,
    AnalysisRunParams,
    analysis_list,
    analysis_run,
)
from suite_backend.ipc.handlers.feature_cmds import FeatureExtractParams, features_extract
from tests._ml_helpers import seed_two_class_recording


def test_analysis_descriptive_and_compare(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)
    features_extract(
        FeatureExtractParams(study_id=study_id, recording_id=rid, kind="band_power"),
        ctx,
    )
    desc = analysis_run(
        AnalysisRunParams(study_id=study_id, recording_id=rid, kind="descriptive"),
        ctx,
    )
    assert desc["report"]["kind"] == "descriptive"
    assert desc["report"]["tables"]["features"]

    cmp_ = analysis_run(
        AnalysisRunParams(
            study_id=study_id,
            recording_id=rid,
            kind="compare_conditions",
            epochset_id=eid,
        ),
        ctx,
    )
    assert cmp_["report"]["kind"] == "compare_conditions"
    assert cmp_["report"]["summary"].get("conditions")
    listed = analysis_list(AnalysisListParams(study_id=study_id, recording_id=rid), ctx)
    assert len(listed["reports"]) >= 2

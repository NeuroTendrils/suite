"""Phase 14 — analysis / statistics IPC."""

from __future__ import annotations

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.algorithms.analysis import (
    compare_conditions_from_epochs,
    descriptive_from_features,
)


class AnalysisRunParams(BaseModel):
    study_id: str
    recording_id: str
    kind: str = "descriptive"  # descriptive | compare_conditions
    featureset_id: str | None = None
    epochset_id: str | None = None
    channel: str | None = None


class AnalysisListParams(BaseModel):
    study_id: str
    recording_id: str | None = None


class AnalysisGetParams(BaseModel):
    study_id: str
    report_id: str


@REGISTRY.register("analysis.run", AnalysisRunParams)
def analysis_run(params: AnalysisRunParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)

    if params.kind == "compare_conditions":
        eid = params.epochset_id
        if not eid:
            sets = ctx.studies.list_epochsets(params.study_id, recording_id=rec.id)
            if not sets:
                raise ValueError("no epochset — create epochs first")
            eid = sets[-1].id
        epset = ctx.studies.get_epochset(params.study_id, eid)
        report = compare_conditions_from_epochs(
            study_id=params.study_id,
            recording=rec,
            epochset=epset,
            channel=params.channel,
        )
    else:
        fid = params.featureset_id
        if not fid:
            sets = ctx.studies.list_featuresets(params.study_id, recording_id=rec.id)
            if not sets:
                raise ValueError("no featureset — extract features first")
            fid = sets[-1].id
        fset = ctx.studies.get_featureset(params.study_id, fid)
        report = descriptive_from_features(
            study_id=params.study_id, recording=rec, featureset=fset
        )

    ctx.studies.save_analysis(params.study_id, report)
    return {"report": report.model_dump(mode="json")}


@REGISTRY.register("analysis.list", AnalysisListParams)
def analysis_list(params: AnalysisListParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    reports = ctx.studies.list_analyses(params.study_id, recording_id=params.recording_id)
    return {
        "reports": [
            {
                "id": r.id,
                "name": r.name,
                "kind": r.kind,
                "recording_id": r.recording_id,
                "summary": r.summary,
                "created_at": r.created_at.isoformat(),
            }
            for r in reports
        ]
    }


@REGISTRY.register("analysis.get", AnalysisGetParams)
def analysis_get(params: AnalysisGetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    return ctx.studies.get_analysis(params.study_id, params.report_id).model_dump(mode="json")

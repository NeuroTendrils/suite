"""Phase 13 — feature extract / list / get."""

from __future__ import annotations

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.algorithms.feature_extraction import extract_features


class FeatureExtractParams(BaseModel):
    study_id: str
    recording_id: str
    kind: str = "band_power"  # band_power | psd | connectivity | erp
    parameters: dict = Field(default_factory=dict)
    epochset_id: str | None = None
    export_csv: bool = True


class FeatureListParams(BaseModel):
    study_id: str
    recording_id: str | None = None


class FeatureGetParams(BaseModel):
    study_id: str
    featureset_id: str


@REGISTRY.register("features.extract", FeatureExtractParams)
def features_extract(params: FeatureExtractParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
    epochset = None
    if params.epochset_id:
        epochset = ctx.studies.get_epochset(params.study_id, params.epochset_id)
    export_dir = None
    if params.export_csv:
        export_dir = ctx.workspace.study_dir(params.study_id) / "features" / "exports"
    fset = extract_features(
        study_id=params.study_id,
        recording=rec,
        streams=streams,
        kind=params.kind,
        epochset=epochset,
        parameters=params.parameters,
        export_dir=export_dir,
    )
    if epochset is not None:
        fset.parent_epochset_id = epochset.id
    ctx.studies.save_featureset(params.study_id, fset)
    return {
        "featureset": fset.model_dump(mode="json"),
        "n_features": len(fset.feature_names),
    }


@REGISTRY.register("features.list", FeatureListParams)
def features_list(params: FeatureListParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    sets = ctx.studies.list_featuresets(params.study_id, recording_id=params.recording_id)
    return {
        "featuresets": [
            {
                "id": f.id,
                "name": f.name,
                "kind": f.kind,
                "recording_id": f.recording_id,
                "n_features": len(f.feature_names),
                "export_paths": f.export_paths,
                "created_at": f.created_at.isoformat(),
            }
            for f in sets
        ]
    }


@REGISTRY.register("features.get", FeatureGetParams)
def features_get(params: FeatureGetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    return ctx.studies.get_featureset(params.study_id, params.featureset_id).model_dump(
        mode="json"
    )

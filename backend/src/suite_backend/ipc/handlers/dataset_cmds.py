"""Phases 15–16 — ML dataset builder + leakage-safe splits."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal

from suite_backend.app_context import AppContext
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.scientific.algorithms.ml_dataset import (
    build_from_epochs,
    build_from_featureset,
    build_multimodal,
)
from suite_backend.scientific.algorithms.splits import (
    make_stratified_trial_split,
    make_subject_split,
    split_definition_dict,
)


class DatasetBuildParams(BaseModel):
    study_id: str
    recording_id: str | None = None
    source: str = "epochs"  # epochs | featureset | multimodal
    epochset_id: str | None = None
    featureset_id: str | None = None
    name: str = "dataset"


class DatasetListParams(BaseModel):
    study_id: str


class DatasetGetParams(BaseModel):
    study_id: str
    dataset_id: str


class SplitCreateParams(BaseModel):
    study_id: str
    dataset_id: str
    method: Literal["subject", "stratified_trial"] = "subject"  # subject | stratified_trial
    val_frac: float = 0.15
    test_frac: float = 0.2
    seed: int = 0


class SplitListParams(BaseModel):
    study_id: str
    dataset_id: str | None = None


@REGISTRY.register("datasets.build", DatasetBuildParams)
def datasets_build(params: DatasetBuildParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    out_dir = ctx.workspace.study_dir(params.study_id) / "datasets" / "arrays"

    if params.source == "featureset":
        fid = params.featureset_id
        if not fid:
            sets = ctx.studies.list_featuresets(params.study_id, recording_id=params.recording_id)
            if not sets:
                raise ValueError("no featureset")
            fid = sets[-1].id
        fset = ctx.studies.get_featureset(params.study_id, fid)
        ds = build_from_featureset(
            study_id=params.study_id, featureset=fset, out_dir=out_dir, name=params.name
        )
    else:
        eid = params.epochset_id
        if not eid:
            if not params.recording_id:
                raise ValueError("recording_id or epochset_id required")
            sets = ctx.studies.list_epochsets(params.study_id, recording_id=params.recording_id)
            if not sets:
                raise ValueError("no epochset — create epochs first")
            eid = sets[-1].id
        epset = ctx.studies.get_epochset(params.study_id, eid)
        if params.source == "multimodal":
            study = ctx.studies.get_study(params.study_id)
            rec = find_recording(study, epset.recording_id)
            streams = ctx.studies.list_streams(params.study_id, recording_id=rec.id)
            ds = build_multimodal(
                study_id=params.study_id,
                epochset=epset,
                streams=streams,
                out_dir=out_dir,
                name=params.name,
            )
        else:
            ds = build_from_epochs(
                study_id=params.study_id, epochset=epset, out_dir=out_dir, name=params.name
            )

    ctx.studies.save_mldataset(params.study_id, ds)
    return {"dataset": ds.model_dump(mode="json")}


@REGISTRY.register("datasets.list", DatasetListParams)
def datasets_list(params: DatasetListParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    return {
        "datasets": [
            {
                "id": d.id,
                "name": d.name,
                "source": d.source,
                "n_samples": d.n_samples,
                "n_features": d.n_features,
                "label_names": d.label_names,
                "modalities": d.modalities,
                "created_at": d.created_at.isoformat(),
            }
            for d in ctx.studies.list_mldatasets(params.study_id)
        ]
    }


@REGISTRY.register("datasets.get", DatasetGetParams)
def datasets_get(params: DatasetGetParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    return ctx.studies.get_mldataset(params.study_id, params.dataset_id).model_dump(mode="json")


@REGISTRY.register("datasets.splits.create", SplitCreateParams)
def splits_create(params: SplitCreateParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    ds = ctx.studies.get_mldataset(params.study_id, params.dataset_id)
    if params.method == "stratified_trial":
        split = make_stratified_trial_split(
            ds,
            study_id=params.study_id,
            val_frac=params.val_frac,
            test_frac=params.test_frac,
            seed=params.seed,
        )
    else:
        split = make_subject_split(
            ds,
            study_id=params.study_id,
            val_frac=params.val_frac,
            test_frac=params.test_frac,
            seed=params.seed,
        )
    ctx.studies.save_split(params.study_id, split)
    ds.split_ids = list(ds.split_ids or []) + [split.id]
    ctx.studies.save_mldataset(params.study_id, ds)
    return {
        "split": split.model_dump(mode="json"),
        "split_definition": split_definition_dict(split),
    }


@REGISTRY.register("datasets.splits.list", SplitListParams)
def splits_list(params: SplitListParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    splits = ctx.studies.list_splits(params.study_id, dataset_id=params.dataset_id)
    return {"splits": [s.model_dump(mode="json") for s in splits]}

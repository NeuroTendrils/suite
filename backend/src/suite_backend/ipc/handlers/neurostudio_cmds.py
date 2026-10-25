"""NeuroStudio IPC — templates, experiments, train/eval/infer/explain/export/report."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Experiment
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neurostudio import evaluation, explainability, export as export_mod
from suite_backend.neurostudio import generalization, hyperparameter_search, inference
from suite_backend.neurostudio import model_training, reporting
from suite_backend.neurostudio.templates import catalog
from suite_backend.scientific.algorithms.splits import split_definition_dict


class Empty(BaseModel):
    pass


class TemplateGetParams(BaseModel):
    template_id: str


class RecommendTemplatesParams(BaseModel):
    study_id: str | None = None
    artifact_id: str | None = None


class ExperimentCreateParams(BaseModel):
    study_id: str
    input_artifact_id: str | None = None  # MLDataset id
    preprocessing_plan_id: str | None = None
    template_id: str = "eegnet"
    split_definition: dict = Field(default_factory=dict)
    parameters: dict = Field(default_factory=dict)
    random_seed: int | None = 0


class ExperimentIdParams(BaseModel):
    study_id: str
    experiment_id: str


class ExperimentListParams(BaseModel):
    study_id: str


class TrainParams(BaseModel):
    study_id: str
    experiment_id: str


class EvalParams(BaseModel):
    study_id: str
    experiment_id: str
    split: str = "test"


class InferParams(BaseModel):
    study_id: str
    experiment_id: str
    dataset_id: str | None = None
    split: Literal["all", "train", "val", "test"] = "all"


class ExplainParams(BaseModel):
    study_id: str
    experiment_id: str
    n_repeats: int = 5


class SplitCheckParams(BaseModel):
    split_definition: dict = Field(default_factory=dict)


class ExportStudyParams(BaseModel):
    study_id: str
    include_samples: bool = False
    deidentify: bool = True


class ReportParams(BaseModel):
    study_id: str
    experiment_id: str | None = None


@REGISTRY.register("neurostudio.templates.list", Empty)
def templates_list(_params: Empty, _ctx: AppContext) -> dict:
    return {"templates": catalog.list_templates()}


@REGISTRY.register("neurostudio.templates.get", TemplateGetParams)
def templates_get(params: TemplateGetParams, _ctx: AppContext) -> dict:
    return catalog.get_template(params.template_id)


@REGISTRY.register("neurostudio.templates.recommend", RecommendTemplatesParams)
def templates_recommend(params: RecommendTemplatesParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id) if params.study_id else None
    return catalog.recommend_templates(study=study)


@REGISTRY.register("neurostudio.experiments.create", ExperimentCreateParams)
def experiments_create(params: ExperimentCreateParams, ctx: AppContext) -> dict:
    split_def = dict(params.split_definition or {})
    # attach split indices if split_id provided
    if split_def.get("split_id"):
        split = ctx.studies.get_split(params.study_id, split_def["split_id"])
        split_def = {**split_definition_dict(split), "split_id": split.id}
    leakage = generalization.detect_leakage(split_def)
    exp = Experiment(
        study_id=params.study_id,
        input_artifact_id=params.input_artifact_id,
        preprocessing_plan_id=params.preprocessing_plan_id,
        template_id=params.template_id,
        split_definition=split_def,
        parameters=params.parameters,
        random_seed=params.random_seed,
        results={"leakage_check": leakage},
    )
    study = ctx.studies.get_study(params.study_id)
    study.experiment_ids.append(exp.id)
    ctx.studies.save_study(study)
    ctx.studies.save_experiment(params.study_id, exp)
    return {"experiment": exp.model_dump(mode="json"), "leakage_check": leakage}


@REGISTRY.register("neurostudio.experiments.list", ExperimentListParams)
def experiments_list(params: ExperimentListParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    exps = ctx.studies.list_experiments(params.study_id)
    return {
        "experiments": [
            {
                "id": e.id,
                "template_id": e.template_id,
                "input_artifact_id": e.input_artifact_id,
                "metrics": e.metrics,
                "model": e.model,
                "split_id": (e.split_definition or {}).get("split_id"),
                "leakage_check": (e.results or {}).get("leakage_check"),
                "created_at": e.created_at.isoformat(),
            }
            for e in exps
        ]
    }


@REGISTRY.register("neurostudio.experiments.get", ExperimentIdParams)
def experiments_get(params: ExperimentIdParams, ctx: AppContext) -> dict:
    ctx.studies.get_study(params.study_id)
    return ctx.studies.get_experiment(params.study_id, params.experiment_id).model_dump(
        mode="json"
    )


@REGISTRY.register("neurostudio.train.start", TrainParams)
def train_start(params: TrainParams, ctx: AppContext) -> dict:
    return model_training.train(
        study_id=params.study_id, experiment_id=params.experiment_id, ctx=ctx
    )


@REGISTRY.register("neurostudio.hypertune.start", TrainParams)
def hypertune_start(params: TrainParams, _ctx: AppContext) -> dict:
    return hyperparameter_search.search(
        study_id=params.study_id, experiment_id=params.experiment_id
    )


@REGISTRY.register("neurostudio.eval.run", EvalParams)
def eval_run(params: EvalParams, ctx: AppContext) -> dict:
    return evaluation.evaluate(
        study_id=params.study_id,
        experiment_id=params.experiment_id,
        ctx=ctx,
        split=params.split,
    )


@REGISTRY.register("neurostudio.generalization.run", TrainParams)
def generalization_run(params: TrainParams, ctx: AppContext) -> dict:
    # subject-wise eval = evaluate on test split when available
    out = evaluation.evaluate(
        study_id=params.study_id,
        experiment_id=params.experiment_id,
        ctx=ctx,
        split="test",
    )
    out["kind"] = "subject_generalization_proxy"
    return out


@REGISTRY.register("neurostudio.model.export", TrainParams)
def model_export(params: TrainParams, ctx: AppContext) -> dict:
    return export_mod.export_model_bundle(
        study_id=params.study_id, experiment_id=params.experiment_id, ctx=ctx
    )


@REGISTRY.register("neurostudio.infer.run", InferParams)
def infer_run(params: InferParams, ctx: AppContext) -> dict:
    return inference.run_inference(
        study_id=params.study_id,
        experiment_id=params.experiment_id,
        ctx=ctx,
        dataset_id=params.dataset_id,
        split=params.split,
    )


@REGISTRY.register("neurostudio.explain.run", ExplainParams)
def explain_run(params: ExplainParams, ctx: AppContext) -> dict:
    return explainability.explain_model(
        study_id=params.study_id,
        experiment_id=params.experiment_id,
        ctx=ctx,
        n_repeats=params.n_repeats,
    )


@REGISTRY.register("neurostudio.leakage.check", SplitCheckParams)
def leakage_check(params: SplitCheckParams, _ctx: AppContext) -> dict:
    return generalization.detect_leakage(params.split_definition)


@REGISTRY.register("neurostudio.report.build", ReportParams)
def report_build(params: ReportParams, ctx: AppContext) -> dict:
    if params.experiment_id:
        return reporting.build_experiment_report(
            study_id=params.study_id, experiment_id=params.experiment_id, ctx=ctx
        )
    return reporting.build_study_summary(study_id=params.study_id, ctx=ctx)


@REGISTRY.register("study.export", ExportStudyParams)
def study_export(params: ExportStudyParams, ctx: AppContext) -> dict:
    return export_mod.export_study_package(
        study_id=params.study_id,
        ctx=ctx,
        include_samples=params.include_samples,
        deidentify=params.deidentify,
    )

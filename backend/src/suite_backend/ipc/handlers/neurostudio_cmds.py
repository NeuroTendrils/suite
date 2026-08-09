from __future__ import annotations

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Experiment
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neurostudio import export as export_mod
from suite_backend.neurostudio import generalization, hyperparameter_search, inference
from suite_backend.neurostudio import model_training
from suite_backend.neurostudio.templates import catalog


class Empty(BaseModel):
    pass


class TemplateGetParams(BaseModel):
    template_id: str


class RecommendTemplatesParams(BaseModel):
    study_id: str | None = None
    artifact_id: str | None = None


class ExperimentCreateParams(BaseModel):
    study_id: str
    input_artifact_id: str | None = None
    preprocessing_plan_id: str | None = None
    template_id: str
    split_definition: dict = Field(default_factory=dict)
    parameters: dict = Field(default_factory=dict)
    random_seed: int | None = 0


class TrainParams(BaseModel):
    study_id: str
    experiment_id: str


class SplitCheckParams(BaseModel):
    split_definition: dict = Field(default_factory=dict)


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
    leakage = generalization.detect_leakage(params.split_definition)
    exp = Experiment(
        study_id=params.study_id,
        input_artifact_id=params.input_artifact_id,
        preprocessing_plan_id=params.preprocessing_plan_id,
        template_id=params.template_id,
        split_definition=params.split_definition,
        parameters=params.parameters,
        random_seed=params.random_seed,
        results={"leakage_check": leakage},
    )
    study = ctx.studies.get_study(params.study_id)
    study.experiment_ids.append(exp.id)
    ctx.studies.save_study(study)
    # persist experiment json
    path = ctx.workspace.study_dir(params.study_id) / "experiments" / f"{exp.id}.json"
    path.write_text(exp.model_dump_json(indent=2), encoding="utf-8")
    return {"experiment": exp.model_dump(mode="json"), "leakage_check": leakage}


@REGISTRY.register("neurostudio.train.start", TrainParams)
def train_start(params: TrainParams, _ctx: AppContext) -> dict:
    return model_training.train(study_id=params.study_id, experiment_id=params.experiment_id)


@REGISTRY.register("neurostudio.hypertune.start", TrainParams)
def hypertune_start(params: TrainParams, _ctx: AppContext) -> dict:
    return hyperparameter_search.search(
        study_id=params.study_id, experiment_id=params.experiment_id
    )


@REGISTRY.register("neurostudio.eval.run", TrainParams)
def eval_run(params: TrainParams, _ctx: AppContext) -> dict:
    return {"status": "not_implemented"}


@REGISTRY.register("neurostudio.generalization.run", TrainParams)
def generalization_run(params: TrainParams, _ctx: AppContext) -> dict:
    return generalization.evaluate_subject_generalization(
        study_id=params.study_id, experiment_id=params.experiment_id
    )


@REGISTRY.register("neurostudio.model.export", TrainParams)
def model_export(params: TrainParams, _ctx: AppContext) -> dict:
    return export_mod.export_model_bundle(
        study_id=params.study_id, experiment_id=params.experiment_id
    )


@REGISTRY.register("neurostudio.infer.run", TrainParams)
def infer_run(params: TrainParams, _ctx: AppContext) -> dict:
    return inference.run_inference(study_id=params.study_id, experiment_id=params.experiment_id)


@REGISTRY.register("neurostudio.leakage.check", SplitCheckParams)
def leakage_check(params: SplitCheckParams, _ctx: AppContext) -> dict:
    return generalization.detect_leakage(params.split_definition)

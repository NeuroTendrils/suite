from __future__ import annotations

from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.domain.models import ProcessingPlan, ProcessingStep
from suite_backend.domain.queries import find_recording
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neuroflow.plan_executor import execute_plan
from suite_backend.scientific.algorithms.artifact_detection import detect_artifacts
from suite_backend.scientific.algorithms.augmentation import augment_dataset
from suite_backend.scientific.algorithms.lab_interference import detect_lab_interference
from suite_backend.scientific.algorithms.preprocessing_recommendations import (
    recommend_preprocessing,
)


class RecommendPreprocessingParams(BaseModel):
    study_id: str
    recording_id: str


class PlanCreateParams(BaseModel):
    study_id: str
    name: str
    steps: list[dict] = Field(default_factory=list)


class PlanListParams(BaseModel):
    study_id: str


class PlanExecuteParams(BaseModel):
    study_id: str
    plan_id: str
    recording_id: str


class ArtifactDetectParams(BaseModel):
    study_id: str
    recording_id: str


class AugmentParams(BaseModel):
    study_id: str
    recording_id: str
    strategy: str = "composition"
    parameters: dict = Field(default_factory=dict)


@REGISTRY.register("neuroflow.recommend_preprocessing", RecommendPreprocessingParams)
def recommend(params: RecommendPreprocessingParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return recommend_preprocessing(rec).model_dump(mode="json")


@REGISTRY.register("neuroflow.detect_artifacts", ArtifactDetectParams)
def artifacts(params: ArtifactDetectParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return detect_artifacts(rec).model_dump(mode="json")


@REGISTRY.register("neuroflow.detect_lab_interference", ArtifactDetectParams)
def lab(params: ArtifactDetectParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    rec = find_recording(study, params.recording_id)
    return detect_lab_interference(rec).model_dump(mode="json")


@REGISTRY.register("plans.create", PlanCreateParams)
def plans_create(params: PlanCreateParams, ctx: AppContext) -> dict:
    steps = [
        ProcessingStep(
            operation=s["operation"],
            parameters=s.get("parameters", {}),
            input_requirements=s.get("input_requirements", []),
            output_type=s.get("output_type", "recording_artifact"),
        )
        for s in params.steps
    ]
    plan = ProcessingPlan(name=params.name, steps=steps)
    ctx.studies.save_plan(params.study_id, plan)
    return plan.model_dump(mode="json")


@REGISTRY.register("plans.list", PlanListParams)
def plans_list(params: PlanListParams, ctx: AppContext) -> dict:
    return {
        "plans": [p.model_dump(mode="json") for p in ctx.studies.list_plans(params.study_id)]
    }


@REGISTRY.register("plans.execute", PlanExecuteParams)
def plans_execute(params: PlanExecuteParams, ctx: AppContext) -> dict:
    study = ctx.studies.get_study(params.study_id)
    recording = find_recording(study, params.recording_id)
    plans = {p.id: p for p in ctx.studies.list_plans(params.study_id)}
    if params.plan_id not in plans:
        raise KeyError(f"plan not found: {params.plan_id}")
    artifacts = execute_plan(
        study_id=params.study_id,
        plan=plans[params.plan_id],
        recording=recording,
        repo=ctx.studies,
    )
    return {"artifacts": [a.model_dump(mode="json") for a in artifacts]}


@REGISTRY.register("augmentation.run", AugmentParams)
def augmentation_run(params: AugmentParams, ctx: AppContext) -> dict:
    # Enforce derived-artifact contract; ML team implements algorithms.
    _ = ctx.studies.get_study(params.study_id)
    result = augment_dataset(
        study_id=params.study_id,
        recording_id=params.recording_id,
        strategy=params.strategy,
        parameters=params.parameters,
    )
    return result

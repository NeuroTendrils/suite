"""Batch + recipe IPC commands.

Copyright 2026 NeuroTendrils
Proprietary — see LICENSE.

Adds four allowlisted commands:

    batch.preview   resolve scope + eligibility, write nothing
    batch.execute   apply a plan across the scope, isolated per recording
    recipe.export   serialize a plan to a portable, shareable document
    recipe.import   validate and install a recipe into a study

Recipes are how a validated pipeline moves between studies, machines, and
labs. They are plain JSON with a schema version so an old recipe opened by a
newer build fails loudly instead of half-applying.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from suite_backend import __version__
from suite_backend.app_context import AppContext
from suite_backend.domain.models import ProcessingPlan, ProcessingStep
from suite_backend.ipc.registry import REGISTRY
from suite_backend.neuroflow.batch import preview_batch, run_batch

RECIPE_SCHEMA_VERSION = 1


class BatchScope(BaseModel):
    """Conjunctive filters. All empty means the whole study."""

    subject_ids: list[str] | None = None
    session_ids: list[str] | None = None
    recording_ids: list[str] | None = None
    modality: str | None = None


class BatchPreviewParams(BaseModel):
    study_id: str
    plan_id: str
    scope: BatchScope = Field(default_factory=BatchScope)
    force: bool = False


class BatchExecuteParams(BaseModel):
    study_id: str
    plan_id: str
    scope: BatchScope = Field(default_factory=BatchScope)
    force: bool = False
    stop_on_error: bool = False


class RecipeExportParams(BaseModel):
    study_id: str
    plan_id: str
    author: str | None = None
    notes: str | None = None


class RecipeImportParams(BaseModel):
    study_id: str
    recipe: dict[str, Any]
    name: str | None = None


def _load_plan(ctx: AppContext, study_id: str, plan_id: str) -> ProcessingPlan:
    plans = {p.id: p for p in ctx.studies.list_plans(study_id)}
    if plan_id not in plans:
        raise KeyError(f"plan not found: {plan_id}")
    return plans[plan_id]


@REGISTRY.register("batch.preview", BatchPreviewParams)
def batch_preview(params: BatchPreviewParams, ctx: AppContext) -> dict:
    """Dry run: what would this plan do across the study?"""
    study = ctx.studies.get_study(params.study_id)
    plan = _load_plan(ctx, params.study_id, params.plan_id)
    report = preview_batch(
        study=study,
        plan=plan,
        repo=ctx.studies,
        scope=params.scope.model_dump(exclude_none=True),
        force=params.force,
    )
    return report.to_dict()


@REGISTRY.register("batch.execute", BatchExecuteParams)
def batch_execute(params: BatchExecuteParams, ctx: AppContext) -> dict:
    """Apply a plan across the scope. Always returns a complete report."""
    study = ctx.studies.get_study(params.study_id)
    plan = _load_plan(ctx, params.study_id, params.plan_id)
    report = run_batch(
        study=study,
        plan=plan,
        repo=ctx.studies,
        scope=params.scope.model_dump(exclude_none=True),
        force=params.force,
        stop_on_error=params.stop_on_error,
    )
    return report.to_dict()


@REGISTRY.register("recipe.export", RecipeExportParams)
def recipe_export(params: RecipeExportParams, ctx: AppContext) -> dict:
    """Serialize a plan into a portable recipe document."""
    ctx.studies.get_study(params.study_id)
    plan = _load_plan(ctx, params.study_id, params.plan_id)

    steps = [
        {
            "operation": s.operation,
            "parameters": s.parameters,
            "input_requirements": list(s.input_requirements or []),
            "output_type": s.output_type,
        }
        for s in plan.steps
    ]
    body = {
        "schema_version": RECIPE_SCHEMA_VERSION,
        "name": plan.name,
        "steps": steps,
        "created_with": __version__,
        "author": params.author,
        "notes": params.notes,
    }
    # Checksum covers the steps only, so identical pipelines authored by
    # different people compare equal.
    digest = hashlib.sha256(
        json.dumps(steps, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    body["steps_checksum"] = digest
    return {"recipe": body}


@REGISTRY.register("recipe.import", RecipeImportParams)
def recipe_import(params: RecipeImportParams, ctx: AppContext) -> dict:
    """Validate a recipe and install it as a plan in this study."""
    ctx.studies.get_study(params.study_id)
    recipe = params.recipe

    version = recipe.get("schema_version")
    if version != RECIPE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported recipe schema_version {version!r} "
            f"(this build reads {RECIPE_SCHEMA_VERSION})"
        )

    raw_steps = recipe.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("recipe contains no steps")

    expected = recipe.get("steps_checksum")
    if expected:
        actual = hashlib.sha256(
            json.dumps(raw_steps, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if actual != expected:
            raise ValueError("recipe checksum mismatch — the steps were modified")

    steps: list[ProcessingStep] = []
    for index, step in enumerate(raw_steps):
        if "operation" not in step:
            raise ValueError(f"step {index} has no operation")
        steps.append(
            ProcessingStep(
                operation=step["operation"],
                parameters=step.get("parameters", {}),
                input_requirements=step.get("input_requirements", []),
                output_type=step.get("output_type", "recording_artifact"),
            )
        )

    plan = ProcessingPlan(name=params.name or recipe.get("name", "imported recipe"), steps=steps)
    ctx.studies.save_plan(params.study_id, plan)
    return {
        "plan": plan.model_dump(mode="json"),
        "imported_from": recipe.get("created_with"),
        "author": recipe.get("author"),
    }

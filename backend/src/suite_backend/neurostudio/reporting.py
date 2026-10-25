"""Phase 23 — markdown experiment / study reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Result


def build_experiment_report(
    *,
    study_id: str,
    experiment_id: str,
    ctx: AppContext,
) -> dict[str, Any]:
    study = ctx.studies.get_study(study_id)
    exp = ctx.studies.get_experiment(study_id, experiment_id)
    models = ctx.studies.list_models(study_id, experiment_id=experiment_id)
    results = ctx.studies.list_results(study_id, experiment_id=experiment_id)

    lines = [
        f"# Experiment report — {experiment_id}",
        "",
        f"- Study: **{study.name}** (`{study_id}`)",
        f"- Template: `{exp.template_id}`",
        f"- Input dataset: `{exp.input_artifact_id}`",
        f"- Seed: `{exp.random_seed}`",
        "",
        "## Metrics",
        "",
    ]
    for k, v in sorted((exp.metrics or {}).items()):
        lines.append(f"- `{k}`: {v}")
    if not exp.metrics:
        lines.append("- _(none yet — run eval)_")

    lines.extend(["", "## Models", ""])
    for m in models:
        lines.append(f"- `{m.id}` template={m.template_id} paths={m.paths}")

    lines.extend(["", "## Results", ""])
    for r in results:
        lines.append(f"### {r.kind} (`{r.id}`)")
        lines.append("```json")
        import json

        lines.append(json.dumps(r.payload, indent=2, default=str)[:4000])
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## Provenance notes",
            "",
            "- Raw recordings are never mutated.",
            "- New experiments compare regularized logistic regression and shrinkage LDA with training-only CV.",
            "- EEGNet remains a catalog placeholder. Inspect held-out metrics and leakage warnings before interpreting results.",
            "",
        ]
    )

    md = "\n".join(lines)
    out = ctx.workspace.study_dir(study_id) / "reports" / f"report_{experiment_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    result = Result(
        experiment_id=experiment_id,
        kind="report",
        payload={"markdown_path": str(out), "bytes": len(md.encode())},
    )
    ctx.studies.save_result(study_id, result)
    return {"status": "ok", "path": str(out), "markdown": md, "result_id": result.id}


def build_study_summary(*, study_id: str, ctx: AppContext) -> dict[str, Any]:
    study = ctx.studies.get_study(study_id)
    n_rec = sum(
        len(run.recordings)
        for sub in study.subjects
        for ses in sub.sessions
        for run in ses.runs
    )
    md = "\n".join(
        [
            f"# Study summary — {study.name}",
            "",
            f"- id: `{study.id}`",
            f"- subjects: {len(study.subjects)}",
            f"- recordings: {n_rec}",
            f"- streams: {len(study.stream_ids)}",
            f"- experiments: {len(study.experiment_ids)}",
            f"- plans: {len(study.plan_ids)}",
            "",
        ]
    )
    out = ctx.workspace.study_dir(study_id) / "reports" / f"study_{study_id}_summary.md"
    out.write_text(md, encoding="utf-8")
    return {"status": "ok", "path": str(out), "markdown": md}

"""Phase 24 — export model + study packages."""

from __future__ import annotations

import hashlib
import json
import uuid
import zipfile
from pathlib import Path
from typing import Any

from suite_backend.app_context import AppContext


def export_model_bundle(
    *,
    study_id: str,
    experiment_id: str,
    ctx: AppContext | None = None,
) -> dict[str, Any]:
    if ctx is None:
        return {
            "status": "stub",
            "message": "export requires AppContext — use neurostudio.model.export IPC",
        }

    exp = ctx.studies.get_experiment(study_id, experiment_id)
    model_id = (exp.model or {}).get("model_id")
    if not model_id:
        models = ctx.studies.list_models(study_id, experiment_id=experiment_id)
        if not models:
            return {"status": "error", "message": "no model to export"}
        model_id = models[-1].id
    model = ctx.studies.get_model(study_id, model_id)

    out_dir = ctx.workspace.study_dir(study_id) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{model.id}_bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in (model.paths or {}).values():
            path = Path(p)
            if path.exists():
                zf.write(path, arcname=f"model/{path.name}")
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "study_id": study_id,
                    "experiment": exp.model_dump(mode="json"),
                    "model": model.model_dump(mode="json"),
                    "fingerprint": hashlib.sha256(
                        Path(model.paths.get("joblib", "")).read_bytes()
                        if model.paths.get("joblib") and Path(model.paths["joblib"]).exists()
                        else b""
                    ).hexdigest(),
                },
                indent=2,
                default=str,
            ),
        )
    exp.export_package_ref = str(zip_path)
    ctx.studies.save_experiment(study_id, exp)
    return {
        "status": "ok",
        "path": str(zip_path),
        "model_id": model_id,
        "note": "model + experiment manifest; source raw not included",
    }


def export_study_package(
    *,
    study_id: str,
    ctx: AppContext,
    include_samples: bool = False,
    deidentify: bool = True,
) -> dict[str, Any]:
    """Zip study JSON artifacts (optionally samples)."""
    root = ctx.workspace.study_dir(study_id)
    out_dir = root / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{study_id}_{uuid.uuid4().hex[:10]}_study_export.zip"
    # An allowlist makes metadata-only mean JSON only: never bundles classifiers,
    # raw CSV captures, reports, logs, archives or unrecognized binary formats.
    study = ctx.studies.get_study(study_id)
    # Build a minimal schema instead of trying to blacklist arbitrary PII in JSON.
    # Free-text keys, paths, labels and unknown extension fields never leave here.
    summary = {
        "schema": "neurotendrils.redacted-summary.v1",
        "subjects": len(study.subjects),
        "recordings": sum(
            len(run.recordings)
            for sub in study.subjects
            for ses in sub.sessions
            for run in ses.runs
        ),
        "experiments": [],
    }
    for i, exp in enumerate(ctx.studies.list_experiments(study_id), 1):
        allowed_metrics = {
            f"{part}_{metric}"
            for part in ("train", "val", "test")
            for metric in ("accuracy", "f1_macro")
        }
        summary["experiments"].append(
            {
                "experiment": i,
                "metrics": {
                    key: value
                    for key, value in (exp.metrics or {}).items()
                    if key in allowed_metrics and isinstance(value, (float, int))
                },
            }
        )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root)
            if any(part in {"exports", "logs"} for part in rel.parts):
                continue
            if not include_samples and path.suffix != ".json":
                continue
            if deidentify:
                if path.suffix != ".json":
                    continue
                continue
            else:
                zf.write(path, arcname=str(rel))
        if deidentify:
            zf.writestr("summary.json", json.dumps(summary, indent=2))
        zf.writestr(
            "privacy.json",
            json.dumps(
                {
                    "deidentified": deidentify,
                    "include_samples": include_samples and not deidentify,
                    "note": "Redacted exports contain aggregate counts and selected numeric metrics only. Review before sharing; counts and metrics may still be sensitive.",
                },
                indent=2,
            ),
        )
    return {
        "status": "ok",
        "path": str(zip_path),
        "include_samples": include_samples and not deidentify,
        "deidentified": deidentify,
        "bytes": zip_path.stat().st_size,
    }

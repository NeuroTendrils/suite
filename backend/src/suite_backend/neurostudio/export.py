"""Phase 24 — export model + study packages."""

from __future__ import annotations

import hashlib
import json
import shutil
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
        for key, p in (model.paths or {}).items():
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
) -> dict[str, Any]:
    """Zip study JSON artifacts (optionally samples)."""
    root = ctx.workspace.study_dir(study_id)
    out_dir = root / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{study_id}_study_export.zip"
    skip = {"exports"}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if rel.parts and rel.parts[0] in skip:
                continue
            if not include_samples and (
                path.suffix in {".fif", ".npy", ".fif.gz"} or "samples" in rel.parts
            ):
                # still include small json metadata
                if path.suffix != ".json":
                    continue
            zf.write(path, arcname=str(rel))
    return {
        "status": "ok",
        "path": str(zip_path),
        "include_samples": include_samples,
        "bytes": zip_path.stat().st_size,
    }

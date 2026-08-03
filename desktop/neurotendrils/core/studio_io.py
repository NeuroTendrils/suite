"""NeuroStudio path helpers, recommendation, and train/export directories."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neurotendrils.core.naming import sanitize_base_name, unique_dir
from neurotendrils.core.projectdir import ProjectDir


def template_catalog():
    from neurostudio.templates import catalog

    return catalog()


def find_template(template_id: str):
    from neurostudio.templates import find_template as _find

    return _find(template_id)


def default_config(template_id: str) -> dict[str, Any]:
    from neurostudio.templates import default_config as _defaults

    return _defaults(template_id)


def validate_config(template_id: str, config: dict[str, Any]) -> str | None:
    from neurostudio.templates import validate_config as _validate

    return _validate(template_id, config)


def recommend(dataset_path: str, dataset_kind: str) -> tuple[str, dict[str, str]]:
    """Return (suggested_id, rationales_by_id)."""
    path_lower = dataset_path.lower()
    erp_hints = ("erp", "p300", "oddball", "n400")
    mi_hints = ("mi", "motor", "imagery", "bci")

    scores: dict[str, float] = {
        "eegnet_mi_v1": 1.0,
        "shallow_mi_v1": 0.9,
        "eegnet_erp_v1": 0.8,
    }
    rationales: dict[str, str] = {
        "eegnet_mi_v1": "Compact EEGNet baseline for motor imagery.",
        "shallow_mi_v1": "ShallowConvNet alternative for MI.",
        "eegnet_erp_v1": "EEGNet tuned for ERP / P300-style tasks.",
    }

    if any(h in path_lower for h in erp_hints):
        scores["eegnet_erp_v1"] += 2.0
        rationales["eegnet_erp_v1"] = "Path hints suggest an ERP / P300 dataset."
    if any(h in path_lower for h in mi_hints):
        scores["eegnet_mi_v1"] += 1.5
        scores["shallow_mi_v1"] += 1.2
        rationales["eegnet_mi_v1"] = "Path hints suggest motor imagery."

    sibling = Path(dataset_path).parent / "run.json"
    if sibling.is_file():
        try:
            meta = json.loads(sibling.read_text(encoding="utf-8"))
            plan = meta.get("plan") or {}
            steps = plan.get("steps") or []
            has_epoch = any(s.get("step_id") == "epoch" for s in steps)
            result = meta.get("result") or {}
            if has_epoch or result.get("output_kind") == "epochs":
                scores["eegnet_erp_v1"] += 0.5
                scores["eegnet_mi_v1"] += 0.3
                rationales["eegnet_mi_v1"] = "Sibling run produced epochs; good for supervised templates."
        except (OSError, json.JSONDecodeError):
            pass

    if dataset_kind == "run_output":
        scores["eegnet_mi_v1"] += 0.2

    best = max(scores, key=scores.get)
    return best, rationales


def suggest_train_dir(dataset_path: str, template_id: str) -> Path:
    project = ProjectDir.instance()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = sanitize_base_name(Path(dataset_path).stem, "dataset")
    tmpl = sanitize_base_name(template_id, "template")
    stem = f"studio_{base}_{tmpl}_{stamp}"
    path = project.runs_dir() / stem
    path.mkdir(parents=True, exist_ok=False)
    return path


def suggest_export_dir(template_id: str, fmt: str) -> Path:
    project = ProjectDir.instance()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{sanitize_base_name(template_id, 'model')}_{sanitize_base_name(fmt, 'pt')}_{stamp}"
    return unique_dir(project.models_dir(), stem)


def write_model_sidecar(
    model_dir: Path,
    *,
    template_id: str,
    fmt: str,
    artifact_name: str,
    metrics: dict[str, Any] | None = None,
    title: str | None = None,
) -> Path:
    payload = {
        "kind": "neurostudio_model",
        "v": 1,
        "title": title or f"{template_id} ({fmt})",
        "template_id": template_id,
        "format": fmt,
        "artifact": artifact_name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "publish": {"status": "local"},
    }
    if metrics:
        (model_dir / "metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8"
        )
        payload["metrics"] = {
            "accuracy": metrics.get("accuracy"),
            "balanced_accuracy": metrics.get("balanced_accuracy"),
        }
    path = model_dir / "model.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

"""NeuroStudio path helpers, recommendation, and train/export directories."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neurotendrils.core.naming import sanitize_base_name, unique_dir, unique_path
from neurotendrils.core.projectdir import ProjectDir

CONFIG_KIND = "neurostudio_config"


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


def save_template_config(
    template_id: str,
    config: dict[str, Any],
    *,
    name: str = "",
    dataset_path: str = "",
) -> Path:
    """Persist a tuned template recipe into the project ``templates/`` folder."""
    tmpl = find_template(template_id)
    if tmpl is None:
        raise ValueError(f"Unknown template: {template_id}")
    err = validate_config(template_id, config)
    if err:
        raise ValueError(err)

    project = ProjectDir.instance()
    templates_dir = project.templates_dir()
    templates_dir.mkdir(parents=True, exist_ok=True)

    title = name or str(tmpl.get("title") or template_id)
    stem = sanitize_base_name(title, template_id)
    path = unique_path(templates_dir, stem, ".json")

    payload: dict[str, Any] = {
        "v": 1,
        "kind": CONFIG_KIND,
        "name": title,
        "template_id": template_id,
        "config": deepcopy(config),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    if dataset_path:
        payload["dataset_path"] = dataset_path
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_template_config(path: str | Path) -> dict[str, Any]:
    """Load a saved template config; returns the full payload."""
    project = ProjectDir.instance()
    resolved = project.require_contains(path, "template config")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Invalid template config")
    if data.get("kind") not in {CONFIG_KIND, None}:
        # Accept older drafts that omitted kind if they look like a config.
        if "template_id" not in data or "config" not in data:
            raise ValueError("Not a NeuroStudio template config")
    template_id = str(data.get("template_id") or "")
    if not template_id or find_template(template_id) is None:
        raise ValueError(f"Unknown template: {template_id or '—'}")
    config = data.get("config")
    if not isinstance(config, dict):
        raise ValueError("Template config is missing parameters")
    err = validate_config(template_id, config)
    if err:
        raise ValueError(err)
    return data


def latest_config_for(template_id: str) -> dict[str, Any] | None:
    """Most recently saved config for a built-in template, if any."""
    templates_dir = ProjectDir.instance().templates_dir()
    if not templates_dir.is_dir():
        return None
    newest: tuple[float, dict[str, Any]] | None = None
    for path in templates_dir.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if str(data.get("template_id") or "") != template_id:
            continue
        if not isinstance(data.get("config"), dict):
            continue
        mtime = path.stat().st_mtime
        if newest is None or mtime > newest[0]:
            newest = (mtime, data)
    return None if newest is None else newest[1]


def _path_tokens(path: str) -> set[str]:
    import re

    return {tok for tok in re.split(r"[^a-z0-9]+", Path(path).name.lower()) if tok}


def recommend(dataset_path: str, dataset_kind: str) -> tuple[str, dict[str, str]]:
    """Return (suggested_id, rationales_by_id)."""
    tokens = _path_tokens(dataset_path)
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

    if tokens & set(erp_hints) or any(f"_{h}" in path_lower or f"-{h}" in path_lower for h in erp_hints):
        scores["eegnet_erp_v1"] += 2.0
        rationales["eegnet_erp_v1"] = "Path hints suggest an ERP / P300 dataset."
    if tokens & set(mi_hints):
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
    path = unique_dir(project.runs_dir(), stem)
    path.mkdir(parents=True, exist_ok=False)
    return path


def suggest_export_dir(template_id: str, fmt: str) -> Path:
    project = ProjectDir.instance()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{sanitize_base_name(template_id, 'model')}_{sanitize_base_name(fmt, 'pt')}_{stamp}"
    return unique_dir(project.models_dir(), stem)


def ensure_model_hub_fields(model_dir: Path) -> Path:
    """Merge Hub-facing fields into an existing export sidecar without wiping it."""
    project = ProjectDir.instance()
    safe_dir = project.require_contains(model_dir, "model directory")
    path = safe_dir / "model.json"
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload.setdefault("kind", "neurostudio_model")
    if "v" not in payload and "version" in payload:
        payload["v"] = payload["version"]
    payload.setdefault("v", 1)
    publish = payload.get("publish")
    if not isinstance(publish, dict):
        payload["publish"] = {"status": "local"}
    else:
        publish.setdefault("status", "local")
    payload.setdefault("exported_at", datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

"""Plan generation, validation, and persistence; uses NeuroFlow catalog."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neurotendrils.core.naming import sanitize_base_name, unique_path
from neurotendrils.core.projectdir import ProjectDir

ICA_SEED = 42
TARGET_SFREQ = 250.0
RESAMPLE_IF_ABOVE = 256.0
MIN_CHANNELS_FOR_ICA = 8
MIN_DURATION_FOR_ICA = 30.0


def step_catalog():
    from neuroflow.steps import catalog

    return catalog()


def find_step(step_id: str):
    from neuroflow.steps import find_step as _find

    return _find(step_id)


def default_params(step_id: str) -> dict[str, Any]:
    from neuroflow.steps import default_params as _defaults

    return _defaults(step_id)


def validate_step_params(step_id: str, params: dict[str, Any]) -> str | None:
    from neuroflow.steps import validate_params

    return validate_params(step_id, params)


def make_step(step_id: str, params: dict[str, Any], rationale: str = "") -> dict[str, Any]:
    defn = find_step(step_id)
    title = defn["title"] if defn else step_id
    return {
        "step_id": step_id,
        "title": title,
        "params": deepcopy(params),
        "rationale": rationale,
    }


def from_fingerprint(fingerprint: dict[str, Any]) -> dict[str, Any]:
    if not fingerprint:
        return {"v": 1, "steps": []}

    sfreq = float(fingerprint.get("sfreq") or 0)
    duration = float(fingerprint.get("duration_sec") or 0)
    n_channels = int(fingerprint.get("n_channels") or 0)
    types = fingerprint.get("ch_types") or []
    eeg_like = 0
    for t in types:
        if str(t).lower() in {"eeg", "eog"}:
            eeg_like += 1
    if eeg_like == 0:
        eeg_like = n_channels

    steps: list[dict[str, Any]] = []

    filter_params = default_params("filter")
    if sfreq > 0:
        nyquist = sfreq / 2.0
        h_freq = float(filter_params.get("h_freq") or 0)
        if h_freq >= nyquist:
            filter_params["h_freq"] = max(1.0, nyquist * 0.9)
    steps.append(
        make_step(
            "filter",
            filter_params,
            "Remove slow drift and high-frequency noise before later steps.",
        )
    )

    notch_params = default_params("notch")
    notch_params["freq"] = "60"
    steps.append(make_step("notch", notch_params, "Attenuate power-line interference."))

    if eeg_like >= 2:
        steps.append(
            make_step(
                "reref",
                default_params("reref"),
                "Average reference for multi-channel EEG.",
            )
        )

    if sfreq > RESAMPLE_IF_ABOVE:
        resample_params = default_params("resample")
        resample_params["sfreq"] = TARGET_SFREQ
        steps.append(
            make_step(
                "resample",
                resample_params,
                f"Downsample to {int(TARGET_SFREQ)} Hz after filtering to speed later steps.",
            )
        )

    if n_channels >= MIN_CHANNELS_FOR_ICA and duration >= MIN_DURATION_FOR_ICA:
        steps.append(
            make_step(
                "ica",
                default_params("ica"),
                "Enough channels and duration for an ICA artifact pass.",
            )
        )

    steps.append(
        make_step(
            "epoch",
            default_params("epoch"),
            "Segment continuous data into fixed-length windows.",
        )
    )
    return {"v": 1, "steps": steps}


def validate_plan(plan: dict[str, Any]) -> str | None:
    if not isinstance(plan, dict):
        return "Plan must be a JSON object."
    if int(plan.get("v") or 0) != 1:
        return "Unsupported plan schema version."
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        return "Plan must contain a nonempty steps array."
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return f"Step {index} must be an object."
        step_id = step.get("step_id")
        if not step_id or find_step(str(step_id)) is None:
            return f"Unknown step_id at index {index}."
        params = step.get("params")
        if not isinstance(params, dict):
            return f"Step {step_id}: params must be an object."
        err = validate_step_params(str(step_id), params)
        if err:
            return err
    return None


def save_plan(plan: dict[str, Any], suggested_name: str = "plan") -> Path:
    err = validate_plan(plan)
    if err:
        raise ValueError(err)

    project = ProjectDir.instance()
    stem = sanitize_base_name(suggested_name, "plan")
    if not stem.endswith("_plan"):
        stem = f"{stem}_plan"
    path = unique_path(project.plans_dir(), stem, ".json")

    payload = deepcopy(plan)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    payload.setdefault(
        "reproducibility",
        {
            "schema": 1,
            "seed": ICA_SEED,
            "ica_random_state": ICA_SEED,
            "note": "ICA uses a fixed random_state for reproducible components.",
        },
    )
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_plan(path: str | Path) -> dict[str, Any]:
    project = ProjectDir.instance()
    resolved = project.require_contains(path, "plan")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    err = validate_plan(data)
    if err:
        raise ValueError(err)
    return data


def suggest_run_paths(base_name: str) -> tuple[Path, Path]:
    from datetime import datetime

    project = ProjectDir.instance()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{sanitize_base_name(base_name, 'run')}_{stamp}"
    run_dir = project.runs_dir() / stem
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir / "cleaned.fif", run_dir / "run.json"


def write_run_metadata(
    meta_path: Path,
    *,
    input_path: str,
    output_path: str,
    plan: dict[str, Any],
    result: dict[str, Any],
    plan_path: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "v": 1,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "input_path": input_path,
        "output_path": output_path,
        "plan": plan,
        "result": result,
        "reproducibility": result.get("reproducibility", {}),
    }
    if plan_path:
        payload["plan_path"] = plan_path
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

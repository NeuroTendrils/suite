"""Plan generation, validation, and persistence; uses NeuroFlow catalog."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neurotendrils.core.naming import sanitize_base_name, unique_dir, unique_path
from neurotendrils.core.projectdir import ProjectDir

ICA_SEED = 42
TARGET_SFREQ = 250.0
RESAMPLE_IF_ABOVE = 256.0
MIN_CHANNELS_FOR_ICA = 8
MIN_DURATION_FOR_ICA = 30.0

# Steps that only operate on continuous Raw (must not follow epoching).
_RAW_ONLY_STEPS = frozenset({"filter", "notch", "reref", "resample", "ica"})
_EPOCH_STEPS = frozenset({"epoch", "event_epoch"})
# Steps that require Epochs input.
_EPOCHS_ONLY_STEPS = frozenset({"augment"})

# Task-aware event_epoch window defaults (seconds).
_EPOCH_WINDOWS = {
    "erp": {"tmin": -0.2, "tmax": 0.8, "baseline_tmin": -0.2, "baseline_tmax": 0.0},
    "motor_imagery": {
        "tmin": 0.0,
        "tmax": 4.0,
        "baseline_tmin": 0.0,
        "baseline_tmax": 0.0,
    },
}


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


def _infer_line_freq(fingerprint: dict[str, Any]) -> str:
    """Prefer 50 Hz outside the Americas when fingerprint has no cue."""
    for key in ("line_freq", "power_line_freq"):
        value = fingerprint.get(key)
        if value in (50, 50.0, "50"):
            return "50"
        if value in (60, 60.0, "60"):
            return "60"
    try:
        import locale

        loc = (locale.getlocale()[0] or "").upper()
    except Exception:  # noqa: BLE001
        loc = ""
    # Rough: North America / parts of Asia / South America use 60 Hz.
    if any(tag in loc for tag in ("_US", "_CA", "_MX", "_BR", "_KR", "_TW", "_PH")):
        return "60"
    return "50"


def from_fingerprint(fingerprint: dict[str, Any]) -> dict[str, Any]:
    """Recommend a recipe plan: filter/notch/reref/resample/ICA + event_epoch when labeled."""
    if not fingerprint:
        return {"v": 1, "steps": []}

    sfreq = float(fingerprint.get("sfreq") or 0)
    duration = float(fingerprint.get("duration_sec") or 0)
    n_channels = int(fingerprint.get("n_channels") or 0)
    types = fingerprint.get("ch_types") or []
    eeg_like = sum(1 for t in types if str(t).lower() in {"eeg", "eog"})
    if eeg_like == 0:
        eeg_like = n_channels

    highpass = fingerprint.get("highpass")
    lowpass = fingerprint.get("lowpass")
    steps: list[dict[str, Any]] = []
    mne_kind = str(fingerprint.get("mne_kind") or "raw")

    if mne_kind != "epochs":
        # Skip refiltering when the recording already has a sensible bandpass.
        already_filtered = (
            highpass is not None
            and lowpass is not None
            and float(highpass) >= 0.5
            and float(lowpass) <= 80.0
        )
        if not already_filtered:
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
        notch_params["freq"] = _infer_line_freq(fingerprint)
        steps.append(
            make_step(
                "notch",
                notch_params,
                f"Attenuate ~{notch_params['freq']} Hz power-line interference.",
            )
        )

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

        # Event-locked epochs when prep left annotations/stim events on the file.
        if fingerprint.get("has_events"):
            task = str(fingerprint.get("task_hint") or "erp")
            window = dict(_EPOCH_WINDOWS.get(task, _EPOCH_WINDOWS["erp"]))
            epoch_params = default_params("event_epoch")
            epoch_params.update(window)
            labels = fingerprint.get("annotation_labels") or []
            if labels:
                epoch_params["event_ids"] = ",".join(str(x) for x in labels)
            steps.append(
                make_step(
                    "event_epoch",
                    epoch_params,
                    f"Cut labeled events into epochs ({task} window defaults).",
                )
            )
            # Suggest augment when class coverage looks thin; researcher reviews in UI.
            steps.append(
                make_step(
                    "augment",
                    default_params("augment"),
                    "Suggested fill for scarce/empty class windows (review before/after).",
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
    seen_epoch = False
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return f"Step {index} must be an object."
        step_id = str(step.get("step_id") or "")
        if not step_id or find_step(step_id) is None:
            return f"Unknown step_id at index {index}."
        params = step.get("params")
        if not isinstance(params, dict):
            return f"Step {step_id}: params must be an object."
        err = validate_step_params(step_id, params)
        if err:
            return err
        if step_id in _EPOCHS_ONLY_STEPS and not seen_epoch:
            return (
                f"Step {step_id} at index {index} requires epochs; "
                "add event_epoch (or epoch) earlier in the plan."
            )
        if step_id in _EPOCH_STEPS:
            seen_epoch = True
        elif seen_epoch and step_id in _RAW_ONLY_STEPS:
            return (
                f"Step {step_id} at index {index} cannot run after epoch "
                "(Raw-only step after epoched data)."
            )
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
    project = ProjectDir.instance()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{sanitize_base_name(base_name, 'run')}_{stamp}"
    run_dir = unique_dir(project.runs_dir(), stem)
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
    project_root: str | None = None,
) -> None:
    from neurotendrils.core.projectdir import resolve_path

    if project_root is not None:
        resolved = resolve_path(meta_path)
        root_resolved = resolve_path(project_root)
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            if resolved != root_resolved:
                raise PermissionError(
                    "run metadata must be inside the project folder"
                ) from exc
        safe_meta = resolved
    else:
        safe_meta = ProjectDir.instance().require_contains(meta_path, "run metadata")
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
    safe_meta.parent.mkdir(parents=True, exist_ok=True)
    safe_meta.write_text(json.dumps(payload, indent=2), encoding="utf-8")

"""Execute a NeuroFlow plan against a recording and write cleaned output.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .apply import ApplyError, apply_step
from .repro import run_reproducibility
from .steps import validate_params


class RunError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def run_plan(
    input_path: str | Path,
    output_path: str | Path,
    plan: dict[str, Any],
    *,
    on_progress: Any | None = None,
    should_cancel: Any | None = None,
) -> dict[str, Any]:
    """Load *input_path*, apply plan steps in order, write *output_path*.

    Returns a JSON-serializable result summary (no raw samples).
    *on_progress* is an optional callable(dict) invoked between stages.
    *should_cancel* is an optional callable() -> bool checked between steps.
    """
    in_path = Path(input_path).expanduser()
    out_path = Path(output_path).expanduser()

    if not str(input_path).strip():
        raise RunError("invalid_args", "input_path is required")
    if not str(output_path).strip():
        raise RunError("invalid_args", "output_path is required")
    if not in_path.is_file():
        raise RunError("file_not_found", f"input file not found: {in_path}")

    steps = _normalize_steps(plan)

    def progress(payload: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(payload)

    def cancelled() -> bool:
        return bool(should_cancel and should_cancel())

    try:
        import mne
    except ImportError as exc:
        raise RunError(
            "dependency_missing",
            "mne is required for run; install neuroflow requirements",
        ) from exc

    progress(
        {
            "stage": "load",
            "message": "Loading recording…",
            "index": 0,
            "total": len(steps),
        }
    )
    try:
        data = mne.io.read_raw(str(in_path), preload=True, verbose="ERROR")
    except Exception:
        try:
            data = mne.read_epochs(str(in_path), preload=True, verbose="ERROR")
        except Exception as exc:  # noqa: BLE001
            raise RunError("read_failed", f"failed to read recording: {exc}") from exc

    applied: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if cancelled():
            raise RunError("cancelled", "Run cancelled")
        step_id = step["step_id"]
        params = step["params"]
        hint = ""
        if step_id == "ica":
            hint = " (ICA can take a few minutes on long recordings)"
        progress(
            {
                "stage": "step",
                "message": f"Step {index + 1}/{len(steps)}: {step_id}{hint}",
                "index": index + 1,
                "total": len(steps),
                "step_id": step_id,
            }
        )
        try:
            data = apply_step(
                data,
                step_id,
                params,
                artifacts_dir=str(out_path.parent),
            )
        except ApplyError as exc:
            raise RunError(
                exc.code,
                f"step {index + 1} ({step_id}): {exc.message}",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RunError(
                "step_failed",
                f"step {index + 1} ({step_id}) failed: {exc}",
            ) from exc
        applied.append({"index": index, "step_id": step_id, "params": params})

    if cancelled():
        raise RunError("cancelled", "Run cancelled")

    progress(
        {
            "stage": "save",
            "message": "Writing cleaned output…",
            "index": len(steps),
            "total": len(steps),
        }
    )
    if out_path.exists() and out_path.is_symlink():
        raise RunError("invalid_args", "output_path must not be a symlink")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kind, out_path = _save_output(data, out_path)

    summary: dict[str, Any] = {
        "input_path": str(in_path.resolve()),
        "output_path": str(out_path.resolve()),
        "output_kind": kind,
        "n_steps": len(applied),
        "steps_applied": applied,
        "mne_version": str(getattr(mne, "__version__", "unknown")),
        "reproducibility": run_reproducibility(plan, applied),
    }
    summary.update(_data_summary(data))
    return summary


def _normalize_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(plan, dict):
        raise RunError("invalid_args", "plan must be an object")

    version = plan.get("v", 1)
    if version != 1:
        raise RunError("invalid_args", f"unsupported plan version: {version}")

    steps_value = plan.get("steps")
    if not isinstance(steps_value, list) or not steps_value:
        raise RunError("invalid_args", "plan.steps must be a non-empty array")

    steps: list[dict[str, Any]] = []
    for index, item in enumerate(steps_value):
        if not isinstance(item, dict):
            raise RunError("invalid_args", f"plan.steps[{index}] must be an object")
        step_id = item.get("step_id")
        if not isinstance(step_id, str) or not step_id.strip():
            raise RunError("invalid_args", f"plan.steps[{index}] missing step_id")
        params = item.get("params", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise RunError("invalid_args", f"plan.steps[{index}].params must be an object")
        error = validate_params(step_id, params)
        if error:
            raise RunError("invalid_params", f"plan.steps[{index}]: {error}")
        steps.append({"step_id": step_id, "params": dict(params)})
    return steps


def _save_output(data: Any, out_path: Path) -> tuple[str, Path]:
    import mne

    kind = "epochs" if isinstance(data, mne.Epochs) else "raw"
    # MNE prefers *-epo.fif for Epochs; keep sibling naming consistent.
    if kind == "epochs" and out_path.name == "cleaned.fif":
        out_path = out_path.with_name("cleaned-epo.fif")
    try:
        data.save(str(out_path), overwrite=True, verbose="ERROR")
    except Exception as exc:  # noqa: BLE001
        raise RunError("write_failed", f"failed to write output: {exc}") from exc
    return kind, out_path


def _data_summary(data: Any) -> dict[str, Any]:
    import mne

    info = data.info
    summary: dict[str, Any] = {
        "n_channels": len(info["ch_names"]),
        "sfreq": float(info["sfreq"]),
    }
    if isinstance(data, mne.Epochs):
        summary["n_epochs"] = int(len(data))
        summary["n_times"] = int(len(data.times))
    else:
        summary["n_times"] = int(data.n_times)
        summary["duration_sec"] = float(data.n_times / info["sfreq"]) if info["sfreq"] else 0.0
    return summary

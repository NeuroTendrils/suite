"""NeuroFlow recipe step catalog (source of truth).

Manual prep (crop, montage, pick/drop, bad marks, labels) is NOT catalogued
here — those are Inspector/viewer operations saved onto the recording.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _num(
    id: str,
    label: str,
    default: float | int,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    unit: str = "",
    help: str = "",
    required: bool = True,
) -> dict[str, Any]:
    param: dict[str, Any] = {
        "id": id,
        "label": label,
        "type": "number",
        "default": default,
        "required": required,
    }
    if minimum is not None:
        param["minimum"] = minimum
    if maximum is not None:
        param["maximum"] = maximum
    if unit:
        param["unit"] = unit
    if help:
        param["help"] = help
    return param


def _enum(
    id: str,
    label: str,
    values: list[str],
    default: str,
    *,
    help: str = "",
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "type": "enum",
        "enum": values,
        "default": default,
        "required": True,
        "help": help,
    }


def _bool(id: str, label: str, default: bool, *, help: str = "") -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "type": "boolean",
        "default": default,
        "required": True,
        "help": help,
    }


def _str(
    id: str,
    label: str,
    default: str = "",
    *,
    required: bool = False,
    help: str = "",
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "type": "string",
        "default": default,
        "required": required,
        "help": help,
    }


# Recipe-only catalog. Manual prep stays in the desktop Inspector.
STEPS: list[dict[str, Any]] = [
    {
        "id": "filter",
        "title": "Filter",
        "category": "filtering",
        "description": (
            "Frequency filter (high-pass, low-pass, or band-pass). "
            "Use method=fir for the usual zero-phase FIR path."
        ),
        "params": [
            _num(
                "l_freq",
                "Low cutoff",
                1.0,
                minimum=0.0,
                maximum=500.0,
                unit="Hz",
                help="High-pass edge; 0 disables high-pass.",
            ),
            _num(
                "h_freq",
                "High cutoff",
                40.0,
                minimum=0.0,
                maximum=2000.0,
                unit="Hz",
                help="Low-pass edge; 0 disables low-pass.",
            ),
            _enum(
                "method",
                "Method",
                ["fir", "iir"],
                "fir",
                help="FIR is the usual choice for EEG.",
            ),
        ],
    },
    {
        "id": "notch",
        "title": "Notch filter",
        "category": "filtering",
        "description": "Remove power-line noise (and optional harmonics).",
        "params": [
            _enum(
                "freq",
                "Line frequency",
                ["50", "60"],
                "60",
                help="Mains frequency in Hz.",
            ),
            _bool(
                "harmonics",
                "Include harmonics",
                True,
                help="Also notch 2× and 3× the line frequency.",
            ),
        ],
    },
    {
        "id": "reref",
        "title": "Re-reference",
        "category": "channels",
        "description": "Change the EEG reference.",
        "params": [
            _enum(
                "reference",
                "Reference",
                ["average", "channel"],
                "average",
            ),
            _str(
                "channel",
                "Channel",
                "",
                required=False,
                help="Required when reference is channel (e.g. Cz).",
            ),
        ],
    },
    {
        "id": "resample",
        "title": "Resample",
        "category": "time",
        "description": "Change the sampling rate.",
        "params": [
            _num(
                "sfreq",
                "New sampling rate",
                250.0,
                minimum=1.0,
                maximum=5000.0,
                unit="Hz",
            ),
        ],
    },
    {
        "id": "ica",
        "title": "ICA",
        "category": "artifacts",
        "description": "Fit ICA and exclude obvious artifact components (EOG heuristics).",
        "params": [
            _num(
                "n_components",
                "Components",
                0.99,
                minimum=0.0,
                maximum=512.0,
                help="Float in (0,1] = variance fraction; integer ≥1 = component count.",
            ),
            _bool("find_bads_eog", "Auto-exclude EOG-like", True),
            _str(
                "exclude",
                "Exclude indices",
                "",
                required=False,
                help="Optional comma-separated ICA component indices to drop.",
            ),
        ],
    },
    {
        "id": "event_epoch",
        "title": "Event epoch",
        "category": "epochs",
        "description": (
            "Cut continuous data into event-locked epochs using annotations "
            "or stim events already on the recording (labels come from prep)."
        ),
        "params": [
            _num(
                "tmin",
                "Start",
                -0.2,
                minimum=-10.0,
                maximum=10.0,
                unit="s",
                help="Epoch start relative to event onset.",
            ),
            _num(
                "tmax",
                "End",
                0.8,
                minimum=-9.0,
                maximum=60.0,
                unit="s",
                help="Epoch end relative to event onset.",
            ),
            _num(
                "baseline_tmin",
                "Baseline start",
                -0.2,
                minimum=-10.0,
                maximum=10.0,
                unit="s",
                required=False,
                help="Baseline window start; set equal ends to skip.",
            ),
            _num(
                "baseline_tmax",
                "Baseline end",
                0.0,
                minimum=-10.0,
                maximum=10.0,
                unit="s",
                required=False,
                help="Baseline window end; set equal to baseline_tmin to skip.",
            ),
            _str(
                "event_ids",
                "Event labels",
                "",
                required=False,
                help="Comma-separated annotation names to keep; empty = all non-bad.",
            ),
        ],
    },
    {
        "id": "epoch",
        "title": "Fixed epoch",
        "category": "epochs",
        "description": "Cut continuous data into fixed-length segments (legacy / unlabeled).",
        "params": [
            _num(
                "duration",
                "Epoch length",
                2.0,
                minimum=0.05,
                maximum=3600.0,
                unit="s",
            ),
            _num(
                "overlap",
                "Overlap",
                0.0,
                minimum=0.0,
                maximum=3599.0,
                unit="s",
                help="Must be smaller than epoch length.",
            ),
        ],
    },
    {
        "id": "augment",
        "title": "Augment",
        "category": "epochs",
        "description": (
            "Suggest synthetic trials to fill scarce/empty class windows. "
            "Accepted trials are tagged augmented=true for provenance."
        ),
        "params": [
            _enum(
                "method",
                "Method",
                ["noise", "time_shift", "channel_dropout"],
                "noise",
                help="How to synthesize fill-in trials from existing ones.",
            ),
            _num(
                "per_class_min",
                "Min trials per class",
                8,
                minimum=1,
                maximum=10000,
                help="Augment until each class reaches at least this many trials.",
            ),
            _num(
                "noise_std",
                "Noise scale",
                0.05,
                minimum=0.0,
                maximum=1.0,
                help="Relative Gaussian noise (fraction of per-channel std).",
            ),
            _num(
                "time_shift_frac",
                "Time shift",
                0.05,
                minimum=0.0,
                maximum=0.4,
                help="Max circular shift as a fraction of epoch length.",
            ),
            _num(
                "dropout_frac",
                "Channel dropout",
                0.1,
                minimum=0.0,
                maximum=0.5,
                help="Fraction of channels zeroed for channel_dropout.",
            ),
            _num(
                "seed",
                "Seed",
                42,
                minimum=0,
                maximum=2_147_483_647,
                help="RNG seed for reproducible suggestions.",
            ),
        ],
    },
]


def catalog() -> list[dict[str, Any]]:
    """Return a deep copy of the step catalog."""
    return deepcopy(STEPS)


def find_step(step_id: str) -> dict[str, Any] | None:
    for step in STEPS:
        if step["id"] == step_id:
            return deepcopy(step)
    return None


def default_params(step_id: str) -> dict[str, Any]:
    step = find_step(step_id)
    if step is None:
        return {}
    return {p["id"]: deepcopy(p["default"]) for p in step["params"]}


def validate_params(step_id: str, params: dict[str, Any]) -> str | None:
    """Return an error message, or None if params are valid."""
    step = next((s for s in STEPS if s["id"] == step_id), None)
    if step is None:
        return f"Unknown step: {step_id}"

    for schema in step["params"]:
        key = schema["id"]
        if key not in params:
            if schema.get("required", True):
                return f"Missing parameter “{key}” on step “{step_id}”."
            continue

        value = params[key]
        ptype = schema["type"]

        if ptype == "boolean":
            if not isinstance(value, bool):
                return f"Parameter “{key}” must be a boolean."
        elif ptype == "enum":
            if value not in schema.get("enum", []):
                return f"Parameter “{key}” must be one of: {', '.join(schema['enum'])}."
        elif ptype == "string":
            if not isinstance(value, str):
                return f"Parameter “{key}” must be a string."
            if schema.get("required", True) and not value.strip():
                return f"Parameter “{key}” must not be empty."
        elif ptype in {"number", "integer"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return f"Parameter “{key}” must be a {ptype}."
            number = float(value)
            if ptype == "integer" and abs(number - round(number)) > 1e-9:
                return f"Parameter “{key}” must be an integer."
            if "minimum" in schema and number < schema["minimum"]:
                return f"Parameter “{key}” must be ≥ {schema['minimum']}."
            if "maximum" in schema and number > schema["maximum"]:
                return f"Parameter “{key}” must be ≤ {schema['maximum']}."

    if step_id == "filter":
        low = float(params.get("l_freq", 0))
        high = float(params.get("h_freq", 0))
        if low > 0 and high > 0 and low >= high:
            return "filter: l_freq must be less than h_freq when both are set."

    if step_id == "reref" and params.get("reference") == "channel":
        if not str(params.get("channel", "")).strip():
            return "reref: channel is required when reference is “channel”."

    if step_id == "epoch":
        duration = float(params.get("duration", 0))
        overlap = float(params.get("overlap", 0))
        if overlap >= duration:
            return "epoch: overlap must be smaller than duration."

    if step_id == "event_epoch":
        tmin = float(params.get("tmin", -0.2))
        tmax = float(params.get("tmax", 0.8))
        if tmin >= tmax:
            return "event_epoch: tmin must be less than tmax."

    if step_id == "ica":
        n_components = float(params.get("n_components", 0.99))
        if abs(n_components - round(n_components)) <= 1e-9:
            if int(round(n_components)) < 1:
                return "ica: n_components integer count must be ≥ 1."
        elif n_components <= 0.0 or n_components > 1.0:
            return "ica: n_components variance fraction must be in (0, 1]."

    if step_id == "augment":
        # Augment only makes sense after epochs; order is enforced by plans.py.
        pass

    return None

"""NeuroStudio model template catalog.

Braindecode-style named recipes: model family + hyperparams + train defaults.
Implementations wrap braindecode.models.*

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


def _int(
    id: str,
    label: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    help: str = "",
) -> dict[str, Any]:
    param = _num(
        id,
        label,
        default,
        minimum=float(minimum) if minimum is not None else None,
        maximum=float(maximum) if maximum is not None else None,
        help=help,
    )
    param["type"] = "integer"
    return param


# Minimal v1 catalog — expand later; depth beats sprawl.
TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "eegnet_mi_v1",
        "title": "EEGNet (motor imagery)",
        "task": "motor_imagery",
        "model_family": "eegnet",
        "backend": "braindecode",
        "description": (
            "Compact EEGNet recipe for motor-imagery decoding. "
            "Wraps braindecode.models.EEGNet with MI-oriented defaults."
        ),
        "input": {
            "sfreq_hz": 250.0,
            "notes": "Prefer Flow-cleaned continuous or epoched FIF at ~250 Hz.",
        },
        "hyperparams": [
            _int("F1", "Temporal filters (F1)", 8, minimum=1, maximum=64),
            _int("D", "Depth multiplier (D)", 2, minimum=1, maximum=8),
            _int("kernel_length", "Temporal kernel", 64, minimum=8, maximum=256),
            _num(
                "drop_prob",
                "Dropout",
                0.25,
                minimum=0.0,
                maximum=0.9,
                help="Dropout probability in EEGNet blocks.",
            ),
        ],
        "train": [
            _int("epochs", "Epochs", 40, minimum=1, maximum=500),
            _int("batch_size", "Batch size", 64, minimum=1, maximum=512),
            _num("lr", "Learning rate", 0.001, minimum=1e-6, maximum=1.0),
            _num("weight_decay", "Weight decay", 0.0, minimum=0.0, maximum=1.0),
            _enum(
                "optimizer",
                "Optimizer",
                ["adam", "adamw", "sgd"],
                "adam",
            ),
            _int("seed", "Seed", 42, minimum=0, maximum=2_147_483_647),
        ],
        "metrics": {
            "primary": "accuracy",
            "report": ["accuracy", "balanced_accuracy", "confusion"],
        },
    },
    {
        "id": "shallow_mi_v1",
        "title": "ShallowConvNet (motor imagery)",
        "task": "motor_imagery",
        "model_family": "shallow",
        "backend": "braindecode",
        "description": (
            "Schirrmeister ShallowConvNet-style template for MI. "
            "Good baseline beside EEGNet."
        ),
        "input": {
            "sfreq_hz": 250.0,
            "notes": "Prefer Flow-cleaned data; bandpass in Flow often 4–38 Hz for MI.",
        },
        "hyperparams": [
            _int("n_filters_time", "Temporal filters", 40, minimum=4, maximum=128),
            _int("filter_time_length", "Temporal kernel", 25, minimum=5, maximum=128),
            _int("n_filters_spat", "Spatial filters", 40, minimum=4, maximum=128),
            _num("drop_prob", "Dropout", 0.5, minimum=0.0, maximum=0.9),
        ],
        "train": [
            _int("epochs", "Epochs", 40, minimum=1, maximum=500),
            _int("batch_size", "Batch size", 64, minimum=1, maximum=512),
            _num("lr", "Learning rate", 0.000625, minimum=1e-6, maximum=1.0),
            _num("weight_decay", "Weight decay", 0.0, minimum=0.0, maximum=1.0),
            _enum(
                "optimizer",
                "Optimizer",
                ["adam", "adamw", "sgd"],
                "adam",
            ),
            _int("seed", "Seed", 42, minimum=0, maximum=2_147_483_647),
        ],
        "metrics": {
            "primary": "accuracy",
            "report": ["accuracy", "balanced_accuracy", "confusion"],
        },
    },
    {
        "id": "eegnet_erp_v1",
        "title": "EEGNet (ERP)",
        "task": "erp",
        "model_family": "eegnet",
        "backend": "braindecode",
        "description": (
            "EEGNet recipe tuned for event-related potential / P300-style tasks."
        ),
        "input": {
            "sfreq_hz": 250.0,
            "notes": "Works best with epoched data around stimulus onsets.",
        },
        "hyperparams": [
            _int("F1", "Temporal filters (F1)", 8, minimum=1, maximum=64),
            _int("D", "Depth multiplier (D)", 2, minimum=1, maximum=8),
            _int("kernel_length", "Temporal kernel", 32, minimum=8, maximum=256),
            _num("drop_prob", "Dropout", 0.25, minimum=0.0, maximum=0.9),
        ],
        "train": [
            _int("epochs", "Epochs", 60, minimum=1, maximum=500),
            _int("batch_size", "Batch size", 32, minimum=1, maximum=512),
            _num("lr", "Learning rate", 0.001, minimum=1e-6, maximum=1.0),
            _num("weight_decay", "Weight decay", 0.0, minimum=0.0, maximum=1.0),
            _enum(
                "optimizer",
                "Optimizer",
                ["adam", "adamw", "sgd"],
                "adam",
            ),
            _int("seed", "Seed", 42, minimum=0, maximum=2_147_483_647),
        ],
        "metrics": {
            "primary": "balanced_accuracy",
            "report": ["accuracy", "balanced_accuracy", "auc", "confusion"],
        },
    },
]


def catalog() -> list[dict[str, Any]]:
    """Return a deep copy of the template catalog."""
    return deepcopy(TEMPLATES)


def find_template(template_id: str) -> dict[str, Any] | None:
    for template in TEMPLATES:
        if template["id"] == template_id:
            return deepcopy(template)
    return None


def default_config(template_id: str) -> dict[str, Any]:
    """Return default hyperparams + train knobs for a template."""
    template = find_template(template_id)
    if template is None:
        return {}
    config: dict[str, Any] = {}
    for group in ("hyperparams", "train"):
        for param in template.get(group, []):
            config[param["id"]] = deepcopy(param["default"])
    return config


def validate_config(template_id: str, config: dict[str, Any]) -> str | None:
    """Return an error message, or None if config is valid."""
    template = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if template is None:
        return f"Unknown template: {template_id}"

    schemas = list(template.get("hyperparams", [])) + list(template.get("train", []))
    for schema in schemas:
        key = schema["id"]
        if key not in config:
            if schema.get("required", True):
                return f"Missing parameter “{key}” on template “{template_id}”."
            continue

        value = config[key]
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

    return None

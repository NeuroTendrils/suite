from __future__ import annotations

from typing import Any


TEMPLATES: list[dict[str, Any]] = [
    {"id": "research_auto", "name": "Regularized EEG baselines", "task_types": ["classification"],
     "input_requirements": {"kind": "features"}, "default_hparams": {}, "search_space": {},
     "status": "ready", "braindecode_ref": None},
    {
        "id": "eegnet",
        "name": "EEGNet",
        "task_types": ["classification"],
        "input_requirements": {"kind": "epochs", "channels": "eeg"},
        "default_hparams": {"dropout": 0.5, "learning_rate": 1e-3},
        "search_space": {"dropout": [0.25, 0.5], "learning_rate": [1e-4, 1e-3]},
        "braindecode_ref": "braindecode.models.EEGNetv4",
        "status": "stub",
    },
    {
        "id": "shallow_fbcsp",
        "name": "ShallowFBCSPNet",
        "task_types": ["classification"],
        "input_requirements": {"kind": "epochs", "channels": "eeg"},
        "default_hparams": {},
        "search_space": {},
        "braindecode_ref": "braindecode.models.ShallowFBCSPNet",
        "status": "stub",
    },
    {
        "id": "deep4",
        "name": "Deep4Net",
        "task_types": ["classification"],
        "input_requirements": {"kind": "epochs", "channels": "eeg"},
        "default_hparams": {},
        "search_space": {},
        "braindecode_ref": "braindecode.models.Deep4Net",
        "status": "stub",
    },
    {
        "id": "custom_placeholder",
        "name": "Custom (ML team)",
        "task_types": ["classification", "regression"],
        "input_requirements": {},
        "default_hparams": {},
        "search_space": {},
        "braindecode_ref": None,
        "status": "stub",
    },
]


def list_templates() -> list[dict[str, Any]]:
    return list(TEMPLATES)


def get_template(template_id: str) -> dict[str, Any]:
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    raise KeyError(template_id)


def recommend_templates(study: Any = None, artifact: Any = None) -> dict[str, Any]:
    """Placeholder recommender — always EEGNet until a real algorithm exists."""
    from suite_backend.neurostudio.templates.model_recommendations import (
        recommend_model_templates,
    )

    return recommend_model_templates(study=study, artifact=artifact)

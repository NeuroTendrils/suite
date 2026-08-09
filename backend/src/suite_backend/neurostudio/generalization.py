from __future__ import annotations

from typing import Any


def evaluate_subject_generalization(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"status": "not_implemented"}


def evaluate_cross_session_generalization(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"status": "not_implemented"}


def evaluate_cross_dataset_generalization(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"status": "not_implemented"}


def detect_leakage(split_definition: dict[str, Any], **_: Any) -> dict[str, Any]:
    """Basic leakage checks on split definitions."""
    warnings: list[str] = []
    train = set(split_definition.get("train_subjects", []))
    val = set(split_definition.get("val_subjects", []))
    test = set(split_definition.get("test_subjects", []))
    if train & val:
        warnings.append("subjects overlap between train and validation")
    if train & test:
        warnings.append("subjects overlap between train and test — potential leakage")
    if val & test:
        warnings.append("subjects overlap between validation and test")
    return {"ok": not warnings, "warnings": warnings}

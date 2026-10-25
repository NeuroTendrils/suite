"""Phase 18 — model evaluation metrics."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Result
from suite_backend.neurostudio.contracts import validate_features, validate_split
from suite_backend.scientific.algorithms.ml_dataset import load_xy


def evaluate(
    *,
    study_id: str,
    experiment_id: str,
    ctx: AppContext,
    split: str = "test",
) -> dict[str, Any]:
    import joblib
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        cohen_kappa_score,
        confusion_matrix,
        f1_score,
    )

    exp = ctx.studies.get_experiment(study_id, experiment_id)
    model_id = (exp.model or {}).get("model_id")
    if not model_id:
        models = ctx.studies.list_models(study_id, experiment_id=experiment_id)
        if not models:
            return {"status": "error", "message": "no trained model for experiment"}
        model_id = models[-1].id
    model = ctx.studies.get_model(study_id, model_id)
    bundle = joblib.load(model.paths["joblib"])
    clf, le = bundle["pipeline"], bundle["label_encoder"]

    dataset_id = exp.input_artifact_id or model.metadata.get("dataset_id")
    dataset = ctx.studies.get_mldataset(study_id, dataset_id)
    X, y = load_xy(dataset)

    validate_features(dataset, bundle["feature_names"], bundle.get("feature_method"))
    if split not in {"train", "val", "test"}:
        return {"status": "error", "message": "split must be train, val or test"}
    split_id = (exp.split_definition or {}).get("split_id")
    if not split_id:
        return {"status": "error", "message": "evaluation requires an explicit split"}
    sp = ctx.studies.get_split(study_id, split_id)
    validate_split(sp, dataset, len(X))
    idx = {"train": sp.train_indices, "val": sp.val_indices, "test": sp.test_indices}[split]
    if not idx:
        return {
            "status": "error",
            "message": f"the {split} split is empty; create a split with held-out samples",
        }
    split_used = split
    warnings = list(sp.leakage_check.get("warnings") or [])
    trained_indices = set(model.metadata.get("train_indices", sp.train_indices))
    if split != "train" and trained_indices.intersection(idx):
        raise ValueError("evaluation samples overlap the model's training samples")
    if split == "train":
        warnings.append("Training score is optimistic and does not measure generalization")
    Xs, y_true = X[idx], y[idx].astype(str)
    y_pred = le.inverse_transform(clf.predict(Xs))
    classes = sorted(set(le.classes_.tolist()) | set(y_true.tolist()))
    unseen = sorted(set(y_true.tolist()) - set(le.classes_.tolist()))
    if unseen:
        warnings.append("Unseen classes are counted as errors: " + ", ".join(unseen))
    acc = float(accuracy_score(y_true, y_pred))
    f1 = float(f1_score(y_true, y_pred, labels=classes, average="macro", zero_division=0))
    balanced = float(balanced_accuracy_score(y_true, y_pred))
    kappa = float(cohen_kappa_score(y_true, y_pred)) if len(set(y_true) | set(y_pred)) > 1 else None
    if kappa is not None and not np.isfinite(kappa):
        kappa = None
    cm = confusion_matrix(y_true, y_pred, labels=classes).tolist()
    # Wilson interval describes binomial accuracy uncertainty, not independent-subject confidence.
    n = len(idx)
    z = 1.959963984540054
    denom = 1 + z * z / n
    center = (acc + z * z / (2 * n)) / denom
    radius = z * np.sqrt(acc * (1 - acc) / n + z * z / (4 * n * n)) / denom

    payload = {
        "accuracy": acc,
        "f1_macro": f1,
        "confusion_matrix": cm,
        "classes": classes,
        "balanced_accuracy": balanced,
        "cohen_kappa": kappa,
        "accuracy_ci95_wilson": [float(center - radius), float(center + radius)],
        "class_support": {c: int(np.sum(y_true == c)) for c in classes},
        "independent_subjects": bool(
            sp.method == "subject" and sp.leakage_check.get("ok") and split != "train"
        ),
        "uncertainty_note": "Trial-level binomial interval; correlated trials can make it optimistic",
        "n": len(idx),
        "split": split_used,
        "requested_split": split,
        "warnings": warnings,
        "model_id": model_id,
    }
    result = Result(experiment_id=experiment_id, kind="eval", payload=payload)
    ctx.studies.save_result(study_id, result)
    exp.metrics = {
        **(exp.metrics or {}),
        f"{split_used}_accuracy": acc,
        f"{split_used}_f1_macro": f1,
    }
    exp.results = {**(exp.results or {}), "last_eval": payload}
    ctx.studies.save_experiment(study_id, exp)
    return {"status": "ok", "result": result.model_dump(mode="json"), "metrics": payload}

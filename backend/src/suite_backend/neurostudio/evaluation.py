"""Phase 18 — model evaluation metrics."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Result
from suite_backend.scientific.algorithms.ml_dataset import load_xy


def evaluate(
    *,
    study_id: str,
    experiment_id: str,
    ctx: AppContext,
    split: str = "test",
) -> dict[str, Any]:
    import joblib
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

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

    split_id = (exp.split_definition or {}).get("split_id")
    if split_id:
        sp = ctx.studies.get_split(study_id, split_id)
        idx = {"train": sp.train_indices, "val": sp.val_indices, "test": sp.test_indices}.get(
            split, sp.test_indices
        )
        if not idx:
            idx = sp.val_indices or sp.train_indices
    else:
        idx = list(range(X.shape[0]))

    Xs, ys = X[idx], y[idx].astype(str)
    y_true = le.transform([c if c in le.classes_ else le.classes_[0] for c in ys])
    y_pred = clf.predict(Xs)
    acc = float(accuracy_score(y_true, y_pred))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(le.classes_)))).tolist()

    payload = {
        "accuracy": acc,
        "f1_macro": f1,
        "confusion_matrix": cm,
        "classes": le.classes_.tolist(),
        "n": int(len(idx)),
        "split": split,
        "model_id": model_id,
    }
    result = Result(experiment_id=experiment_id, kind="eval", payload=payload)
    ctx.studies.save_result(study_id, result)
    exp.metrics = {**(exp.metrics or {}), f"{split}_accuracy": acc, f"{split}_f1_macro": f1}
    exp.results = {**(exp.results or {}), "last_eval": payload}
    ctx.studies.save_experiment(study_id, exp)
    return {"status": "ok", "result": result.model_dump(mode="json"), "metrics": payload}

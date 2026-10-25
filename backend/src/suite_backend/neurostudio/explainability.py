"""Phase 20 — coefficient / permutation importance for sklearn models."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Result
from suite_backend.neurostudio.contracts import validate_features, validate_split
from suite_backend.scientific.algorithms.ml_dataset import load_xy


def explain_model(
    *,
    study_id: str,
    experiment_id: str,
    ctx: AppContext,
    n_repeats: int = 5,
) -> dict[str, Any]:
    import joblib
    from sklearn.inspection import permutation_importance

    exp = ctx.studies.get_experiment(study_id, experiment_id)
    model_id = (exp.model or {}).get("model_id")
    if not model_id:
        models = ctx.studies.list_models(study_id, experiment_id=experiment_id)
        if not models:
            return {"status": "error", "message": "no model"}
        model_id = models[-1].id
    model = ctx.studies.get_model(study_id, model_id)
    bundle = joblib.load(model.paths["joblib"])
    clf, le = bundle["pipeline"], bundle["label_encoder"]
    feature_names = list(bundle.get("feature_names") or [])

    dataset = ctx.studies.get_mldataset(
        study_id, exp.input_artifact_id or model.metadata.get("dataset_id")
    )
    X, y = load_xy(dataset)
    validate_features(dataset, feature_names, bundle.get("feature_method"))
    split_id = (exp.split_definition or {}).get("split_id")
    if not split_id:
        return {"status": "error", "message": "explanations require an explicit held-out split"}
    split = ctx.studies.get_split(study_id, split_id)
    validate_split(split, dataset, len(X))
    part = "val" if split.val_indices else "test"
    indices = split.val_indices or split.test_indices
    if not indices:
        return {"status": "error", "message": "no held-out samples available for explanation"}
    if set(indices).intersection(model.metadata.get("train_indices", split.train_indices)):
        raise ValueError("explanation samples overlap training samples")
    X, y = X[indices], y[indices].astype(str)
    def score(estimator, features, truth):
        return float(np.mean(le.inverse_transform(estimator.predict(features)) == truth))

    coef_imp: list[dict[str, Any]] = []
    try:
        final = clf.named_steps["clf"]
        coef = np.asarray(final.coef_)
        # mean abs across classes
        mag = np.mean(np.abs(coef), axis=0) if coef.ndim == 2 else np.abs(coef)
        for i, name in enumerate(feature_names[: mag.size]):
            coef_imp.append({"feature": name, "mean_abs_coef": float(mag[i])})
        coef_imp.sort(key=lambda d: d["mean_abs_coef"], reverse=True)
    except Exception:
        coef_imp = []

    perm = permutation_importance(
        clf,
        X,
        y,
        n_repeats=n_repeats,
        random_state=exp.random_seed or 0,
        scoring=score,
    )
    perm_imp = [
        {
            "feature": feature_names[i] if i < len(feature_names) else f"f{i}",
            "importance_mean": float(perm.importances_mean[i]),
            "importance_std": float(perm.importances_std[i]),
        }
        for i in range(len(perm.importances_mean))
    ]
    perm_imp.sort(key=lambda d: d["importance_mean"], reverse=True)

    payload = {
        "model_id": model_id,
        "split": part,
        "n": len(indices),
        "warnings": ["Test samples were inspected; do not tune the model using these explanations"] if part == "test" else [],
        "coefficients": coef_imp[:40],
        "permutation": perm_imp[:40],
        "method": "coef+permutation_importance",
    }
    result = Result(experiment_id=experiment_id, kind="explain", payload=payload)
    ctx.studies.save_result(study_id, result)
    return {"status": "ok", "result": result.model_dump(mode="json"), "explanation": payload}

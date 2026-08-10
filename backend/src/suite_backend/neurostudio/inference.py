"""Phase 22 — run inference with a persisted sklearn model."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Prediction
from suite_backend.scientific.algorithms.ml_dataset import load_xy


def check_compatibility(*, n_channels: int, sfreq: float, expected: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    if expected.get("n_channels") and n_channels != expected["n_channels"]:
        warnings.append("n_channels mismatch")
    if expected.get("sfreq") and abs(sfreq - float(expected["sfreq"])) > 1e-3:
        warnings.append("sfreq mismatch")
    return {"ok": not warnings, "warnings": warnings}


def run_inference(
    *,
    study_id: str,
    experiment_id: str,
    ctx: AppContext | None = None,
    dataset_id: str | None = None,
) -> dict[str, Any]:
    if ctx is None:
        return {"status": "not_implemented", "message": "inference requires AppContext"}

    import joblib

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

    ds_id = dataset_id or exp.input_artifact_id or model.metadata.get("dataset_id")
    dataset = ctx.studies.get_mldataset(study_id, ds_id)
    X, _y = load_xy(dataset)
    if X.shape[1] != len(bundle.get("feature_names") or dataset.feature_names):
        return {
            "status": "error",
            "message": f"feature dim mismatch: got {X.shape[1]}",
        }

    pred_enc = clf.predict(X)
    labels = le.inverse_transform(pred_enc).tolist()
    proba = None
    if hasattr(clf, "predict_proba"):
        try:
            proba = clf.predict_proba(X).astype(float).tolist()
        except Exception:
            proba = None

    prediction = Prediction(
        model_id=model_id,
        target_ref=dataset.id,
        outputs={"labels": labels, "proba": proba, "n": int(X.shape[0])},
    )
    ctx.studies.save_prediction(study_id, prediction)
    return {
        "status": "ok",
        "prediction": prediction.model_dump(mode="json"),
        "labels": labels,
    }

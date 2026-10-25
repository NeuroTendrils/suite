"""Phase 22 — run inference with a persisted sklearn model."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Prediction
from suite_backend.neurostudio.contracts import validate_features, validate_split
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
    split: str = "all",
) -> dict[str, Any]:
    """Predict with the experiment's model, locally (scikit-learn via joblib).

    ``split`` selects samples: ``"all"`` (default) or ``"train"``/``"val"``/``"test"`` from the
    experiment's split. Only held-out samples show how the model does on data it has not seen.
    """
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
    X, y = load_xy(dataset)
    validate_features(dataset, bundle["feature_names"], bundle.get("feature_method"))
    if X.shape[1] != len(bundle["feature_names"]):
        return {
            "status": "error",
            "message": f"feature dim mismatch: got {X.shape[1]}",
        }

    if split == "all":
        indices = list(range(X.shape[0]))
    elif split in ("train", "val", "test"):
        split_id = (exp.split_definition or {}).get("split_id")
        if not split_id:
            return {"status": "error", "message": "experiment has no split; use split='all'"}
        sp = ctx.studies.get_split(study_id, split_id)
        validate_split(sp, dataset, len(X))
        indices = list({"train": sp.train_indices, "val": sp.val_indices, "test": sp.test_indices}[split])
        if not indices:
            return {"status": "error", "message": f"the {split} split is empty"}
    else:
        return {"status": "error", "message": f"unknown split {split!r}"}

    if not indices:
        return {"status": "error", "message": "dataset is empty"}
    Xs = X[indices]
    pred_enc = clf.predict(Xs)
    labels = le.inverse_transform(pred_enc).tolist()
    proba = None
    if hasattr(clf, "predict_proba"):
        try:
            proba = clf.predict_proba(Xs).astype(float).tolist()
        except Exception:
            proba = None
    confidence = [float(max(p)) for p in proba] if proba is not None else None

    prediction = Prediction(
        model_id=model_id,
        target_ref=dataset.id,
        outputs={"labels": labels, "proba": proba, "n": int(Xs.shape[0]), "split": split},
    )
    ctx.studies.save_prediction(study_id, prediction)
    return {
        "status": "ok",
        "prediction": prediction.model_dump(mode="json"),
        "labels": labels,
        "proba": proba,
        "confidence": confidence,
        "classes": le.classes_.tolist(),
        "true_labels": [str(v) for v in y[indices].tolist()],
        "indices": indices,
        "split": split,
        "dataset_id": dataset.id,
        "model_id": model_id,
        "model_kind": model.metadata.get("backend", "sklearn"),
        "template_id": model.template_id,
        "runs_locally": True,
    }

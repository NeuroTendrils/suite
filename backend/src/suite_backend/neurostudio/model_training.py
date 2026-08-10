"""Phase 17 — sklearn training on MLDataset (Braindecode EEGNet remains template/recommend)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.app_context import AppContext
from suite_backend.domain.models import ModelRecord
from suite_backend.scientific.algorithms.ml_dataset import load_xy


def train(
    *,
    study_id: str,
    experiment_id: str,
    ctx: AppContext | None = None,
) -> dict[str, Any]:
    if ctx is None:
        return {
            "status": "error",
            "message": "train requires AppContext (use neurostudio.train.start IPC)",
        }

    exp = ctx.studies.get_experiment(study_id, experiment_id)
    dataset_id = exp.input_artifact_id or (exp.parameters or {}).get("dataset_id")
    if not dataset_id:
        return {"status": "error", "message": "experiment.input_artifact_id must be an MLDataset id"}

    dataset = ctx.studies.get_mldataset(study_id, dataset_id)
    X, y = load_xy(dataset)
    if X.shape[0] < 2:
        return {"status": "error", "message": "need at least 2 samples to train"}

    split_id = (exp.split_definition or {}).get("split_id")
    if split_id:
        split = ctx.studies.get_split(study_id, split_id)
        train_idx = split.train_indices
    else:
        train_idx = list(range(X.shape[0]))
        # hold out last 20% if enough samples
        if len(train_idx) >= 5:
            cut = max(1, int(0.2 * len(train_idx)))
            train_idx = train_idx[:-cut]

    Xtr, ytr = X[train_idx], y[train_idx]
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder, StandardScaler

    le = LabelEncoder()
    y_enc = le.fit_transform(ytr.astype(str))
    if len(set(y_enc.tolist())) < 2:
        # single-class: still fit a dummy constant classifier via duplicated noise class
        return {
            "status": "error",
            "message": "training set has <2 classes — build a multi-condition dataset",
        }

    clf = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=500,
                    random_state=exp.random_seed or 0,
                ),
            ),
        ]
    )
    clf.fit(Xtr, y_enc)

    model_dir = ctx.workspace.study_dir(study_id) / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    import joblib

    model = ModelRecord(
        experiment_id=experiment_id,
        template_id=exp.template_id or "sklearn_logreg",
        metadata={
            "feature_names": dataset.feature_names,
            "classes": le.classes_.tolist(),
            "n_train": int(len(train_idx)),
            "dataset_id": dataset.id,
            "backend": "sklearn",
            "note": "EEGNet template remains recommend-only until Braindecode train lands",
        },
    )
    bundle = model_dir / f"{model.id}.joblib"
    joblib.dump({"pipeline": clf, "label_encoder": le, "feature_names": dataset.feature_names}, bundle)
    model.paths = {"joblib": str(bundle)}
    ctx.studies.save_model(study_id, model)

    exp.model = {"model_id": model.id, "template_id": model.template_id}
    exp.metrics = {**(exp.metrics or {}), "n_train": int(len(train_idx))}
    exp.checkpoints = [str(bundle)]
    ctx.studies.save_experiment(study_id, exp)

    return {
        "status": "ok",
        "model": model.model_dump(mode="json"),
        "n_train": len(train_idx),
        "classes": le.classes_.tolist(),
    }

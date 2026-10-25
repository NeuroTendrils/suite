"""Phase 17 — sklearn training on MLDataset (Braindecode EEGNet remains template/recommend)."""

from __future__ import annotations

from typing import Any

import numpy as np

from suite_backend.app_context import AppContext
from suite_backend.domain.models import ModelRecord
from suite_backend.neurostudio.contracts import validate_split
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
        return {
            "status": "error",
            "message": "experiment.input_artifact_id must be an MLDataset id",
        }

    dataset = ctx.studies.get_mldataset(study_id, dataset_id)
    X, y = load_xy(dataset)
    if X.shape[0] < 2:
        return {"status": "error", "message": "need at least 2 samples to train"}

    split_id = (exp.split_definition or {}).get("split_id")
    if split_id:
        split = ctx.studies.get_split(study_id, split_id)
        validate_split(split, dataset, len(X))
        train_idx = split.train_indices
    else:
        return {
            "status": "error",
            "message": "create an explicit train/validation/test split before training",
        }

    Xtr, ytr = X[train_idx], y[train_idx]
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import LabelEncoder, StandardScaler

    le = LabelEncoder()
    y_enc = le.fit_transform(ytr.astype(str))
    if len(set(y_enc.tolist())) < 2:
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
                    class_weight="balanced",
                ),
            ),
        ]
    )
    # Fit every scaler and candidate inside training folds only. Test data is untouched.
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, StratifiedKFold

    seed = exp.random_seed or 0
    warnings = list(split.leakage_check.get("warnings") or [])
    subjects = np.asarray(dataset.subject_ids)[train_idx]
    sessions = np.asarray([f"{s}/{t}" for s, t in zip(dataset.subject_ids, dataset.session_ids)])[
        train_idx
    ]
    groups = subjects if len(set(subjects)) > 1 else sessions
    counts = np.bincount(y_enc)
    n_folds = min(3, int(counts.min()))
    cv = None
    cv_method = "none"
    if n_folds >= 2:
        if len(set(groups)) >= 2:
            n_folds = min(n_folds, len(set(groups)))
            proposed = list(
                StratifiedGroupKFold(n_folds, shuffle=True, random_state=seed).split(
                    Xtr, y_enc, groups
                )
            )
            if all(
                len(set(y_enc[a])) == len(le.classes_) and len(set(y_enc[b])) == len(le.classes_)
                for a, b in proposed
            ):
                cv, cv_method = proposed, "grouped_training_cv"
            else:
                warnings.append(
                    "Too few independent groups per class for model selection; fixed baseline used"
                )
        else:
            cv = list(StratifiedKFold(n_folds, shuffle=True, random_state=seed).split(Xtr, y_enc))
            cv_method = "trial_training_cv"
            warnings.append(
                "Training CV is within one session; scores do not establish cross-session generalization"
            )
    selected_params = {}
    cv_score = None
    if cv is not None:
        grid = [{"clf__C": [0.01, 0.1, 1.0, 10.0]}]
        if exp.template_id == "research_auto" and all(
            np.bincount(y_enc[a], minlength=len(le.classes_)).min() >= 2 for a, _ in cv
        ):
            grid.append({"clf": [LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")]})
        search = GridSearchCV(
            clf, grid, scoring="balanced_accuracy", cv=cv, n_jobs=1, error_score="raise"
        )
        search.fit(Xtr, y_enc)
        clf = search.best_estimator_
        selected_params = {k: str(v) if k == "clf" else v for k, v in search.best_params_.items()}
        cv_score = float(search.best_score_)
    else:
        clf.fit(Xtr, y_enc)
    actual_template = (
        "sklearn_lda"
        if isinstance(clf.named_steps["clf"], LinearDiscriminantAnalysis)
        else "sklearn_logreg"
    )

    model_dir = ctx.workspace.study_dir(study_id) / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    import joblib

    model = ModelRecord(
        experiment_id=experiment_id,
        # Record the actual estimator, including for legacy template requests.
        template_id=actual_template,
        metadata={
            "requested_template": exp.template_id,
            "feature_names": dataset.feature_names,
            "classes": le.classes_.tolist(),
            "n_train": len(train_idx),
            "dataset_id": dataset.id,
            "backend": "sklearn",
            "note": "Training-only model selection; EEGNet remains recommend-only",
            "train_indices": list(train_idx),
            "split_id": split.id,
            "selection": {
                "method": cv_method,
                "balanced_accuracy": cv_score,
                "parameters": selected_params,
            },
            "warnings": warnings,
            "random_seed": seed,
            "versions": {"numpy": np.__version__, "sklearn": __import__("sklearn").__version__},
        },
    )
    bundle = model_dir / f"{model.id}.joblib"
    joblib.dump(
        {
            "pipeline": clf,
            "label_encoder": le,
            "feature_names": dataset.feature_names,
            "feature_method": dataset.provenance.get("method"),
        },
        bundle,
    )
    model.paths = {"joblib": str(bundle)}
    ctx.studies.save_model(study_id, model)

    exp.model = {"model_id": model.id, "template_id": model.template_id}
    exp.metrics = {**(exp.metrics or {}), "n_train": len(train_idx)}
    exp.checkpoints = [str(bundle)]
    ctx.studies.save_experiment(study_id, exp)

    return {
        "status": "ok",
        "model": model.model_dump(mode="json"),
        "n_train": len(train_idx),
        "classes": le.classes_.tolist(),
    }

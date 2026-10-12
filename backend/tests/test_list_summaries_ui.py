"""List summaries expose what the desktop UI needs to pick the right item.

IDs are random, and list endpoints sort by filename, so list order says nothing
about recency. The UI orders by ``created_at`` and links experiments to their
split, so those fields must be present. Existing keys must be unchanged.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from suite_backend.ipc.handlers.dataset_cmds import (
    DatasetBuildParams,
    DatasetListParams,
    SplitCreateParams,
    datasets_build,
    datasets_list,
    splits_create,
)
from suite_backend.ipc.handlers.epoch_cmds import EpochListParams, epochs_list
from suite_backend.ipc.handlers.neurostudio_cmds import (
    ExperimentCreateParams,
    ExperimentListParams,
    experiments_create,
    experiments_list,
)
from tests._ml_helpers import seed_two_class_recording


def test_list_summaries_include_created_at_and_split(tmp_path: Path) -> None:
    ctx, study_id, rid, eid = seed_two_class_recording(tmp_path)

    epochsets = epochs_list(EpochListParams(study_id=study_id, recording_id=rid), ctx)
    (ep,) = epochsets["epochsets"]
    assert ep["id"] == eid
    assert {"name", "recording_id", "n_trials", "event_names", "tmin", "tmax"} <= ep.keys()
    datetime.fromisoformat(ep["created_at"])

    ds = datasets_build(
        DatasetBuildParams(study_id=study_id, recording_id=rid, epochset_id=eid),
        ctx,
    )["dataset"]
    (listed_ds,) = datasets_list(DatasetListParams(study_id=study_id), ctx)["datasets"]
    assert listed_ds["id"] == ds["id"]
    assert {"name", "source", "n_samples", "n_features", "label_names"} <= listed_ds.keys()
    datetime.fromisoformat(listed_ds["created_at"])

    split = splits_create(
        SplitCreateParams(
            study_id=study_id, dataset_id=ds["id"], method="stratified_trial", seed=0
        ),
        ctx,
    )["split"]
    created = experiments_create(
        ExperimentCreateParams(
            study_id=study_id,
            input_artifact_id=ds["id"],
            split_definition={"split_id": split["id"]},
        ),
        ctx,
    )
    exp = created["experiment"]

    (listed_exp,) = experiments_list(ExperimentListParams(study_id=study_id), ctx)[
        "experiments"
    ]
    assert listed_exp["id"] == exp["id"]
    assert listed_exp["input_artifact_id"] == ds["id"]
    assert listed_exp["split_id"] == split["id"]
    # Single-subject trial split: the stored check must surface the overlap warning.
    assert listed_exp["leakage_check"] == created["leakage_check"]
    assert listed_exp["leakage_check"]["ok"] is False
    assert listed_exp["model"] is None or isinstance(listed_exp["model"], dict)
    datetime.fromisoformat(listed_exp["created_at"])

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.ipc.handlers.event_cmds import (
    EventCreateParams,
    EventDeleteParams,
    EventListParams,
    events_create,
    events_delete,
    events_list,
)
from suite_backend.ipc.handlers.recording_cmds import ImportRecordingParams, import_recording
from suite_backend.ipc.handlers.study_cmds import (
    SubjectAddParams,
    subjects_add,
)


def test_events_crud(tmp_path: Path) -> None:
    mne = pytest.importorskip("mne")
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("Ev")
    added = subjects_add(SubjectAddParams(study_id=study.id, label="S001"), ctx)
    info = mne.create_info(["Fz"], 100.0, ch_types="eeg")
    raw = mne.io.RawArray(np.random.randn(1, 300) * 1e-6, info, verbose=False)
    fif = tmp_path / "e.fif"
    raw.save(fif, overwrite=True, verbose=False)
    eeg = import_recording(
        ImportRecordingParams(
            study_id=study.id,
            subject_id=added["subject"]["id"],
            session_id=added["session_id"],
            run_id=added["run_id"],
            path=str(fif),
        ),
        ctx,
    )
    rid = eeg["recording"]["id"]
    created = events_create(
        EventCreateParams(
            study_id=study.id,
            recording_id=rid,
            timestamp=1.25,
            name="square",
            code="1",
            source="manual",
        ),
        ctx,
    )
    eid = created["event"]["id"]
    listed = events_list(EventListParams(study_id=study.id, recording_id=rid), ctx)
    assert any(e["id"] == eid for e in listed["events"])
    deleted = events_delete(
        EventDeleteParams(study_id=study.id, recording_id=rid, event_id=eid),
        ctx,
    )
    assert deleted["deleted"] == eid
    listed2 = events_list(EventListParams(study_id=study.id, recording_id=rid), ctx)
    assert all(e["id"] != eid for e in listed2["events"])

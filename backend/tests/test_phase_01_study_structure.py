from __future__ import annotations

import json
from pathlib import Path

from suite_backend.app_context import AppContext
from suite_backend.domain.migrate import migrate_study_dict
from suite_backend.domain.models import CURRENT_STUDY_SCHEMA_VERSION, Modality
from suite_backend.ipc.handlers.study_cmds import (
    RunAddParams,
    SessionAddParams,
    StreamListParams,
    SubjectAddParams,
    SubjectMetadataParams,
    runs_add,
    sessions_add,
    streams_list,
    subjects_add,
    subjects_set_metadata,
    studies_tree,
    StudyGetParams,
)
from suite_backend.neurostudio.templates.catalog import recommend_templates
from suite_backend.storage.local import LocalStudyRepository, LocalWorkspace


def test_new_study_is_schema_v2(tmp_path: Path) -> None:
    repo = LocalStudyRepository(LocalWorkspace(tmp_path))
    study = repo.create_study("Demo")
    assert study.schema_version == CURRENT_STUDY_SCHEMA_VERSION
    assert study.stream_ids == []


def test_multi_subject_sessions_runs_metadata(tmp_path: Path) -> None:
    ctx = AppContext(tmp_path)
    study = ctx.studies.create_study("MI")
    a = subjects_add(
        SubjectAddParams(study_id=study.id, label="S001", metadata={"group": "A"}),
        ctx,
    )
    subjects_add(SubjectAddParams(study_id=study.id, label="S002"), ctx)
    subjects_set_metadata(
        SubjectMetadataParams(
            study_id=study.id,
            subject_id=a["subject"]["id"],
            metadata={"handedness": "R"},
            merge=True,
        ),
        ctx,
    )
    ses = sessions_add(
        SessionAddParams(
            study_id=study.id,
            subject_id=a["subject"]["id"],
            name="session-2",
            create_default_run=False,
        ),
        ctx,
    )
    runs_add(
        RunAddParams(
            study_id=study.id,
            subject_id=a["subject"]["id"],
            session_id=ses["session"]["id"],
            name="run-extra",
        ),
        ctx,
    )
    loaded = ctx.studies.get_study(study.id)
    assert len(loaded.subjects) == 2
    sub = next(s for s in loaded.subjects if s.label == "S001")
    assert sub.metadata["group"] == "A"
    assert sub.metadata["handedness"] == "R"
    assert len(sub.sessions) == 2
    assert any(r.name == "run-extra" for s in sub.sessions for r in s.runs)

    tree = studies_tree(StudyGetParams(study_id=study.id), ctx)
    assert tree["stream_count"] == 0
    assert len(tree["subjects"]) == 2


def test_migrate_v1_recording_to_eeg_stream(tmp_path: Path) -> None:
    workspace = LocalWorkspace(tmp_path)
    repo = LocalStudyRepository(workspace)
    # Write a v1 study.json with legacy recording channels (no schema_version / streams)
    study_id = "study_legacytest"
    study_dir = workspace.study_dir(study_id)
    raw = {
        "id": study_id,
        "name": "Legacy",
        "subjects": [
            {
                "id": "sub_1",
                "label": "S001",
                "metadata": {},
                "sessions": [
                    {
                        "id": "ses_1",
                        "name": "session-001",
                        "metadata": {},
                        "runs": [
                            {
                                "id": "run_1",
                                "name": "run-001",
                                "metadata": {},
                                "recordings": [
                                    {
                                        "id": "rec_1",
                                        "subject_id": "sub_1",
                                        "session_id": "ses_1",
                                        "run_id": "run_1",
                                        "source_files": ["/tmp/x.fif"],
                                        "source_format": "fif",
                                        "sampling_rate": 250.0,
                                        "duration": 10.0,
                                        "channel_count": 2,
                                        "channels": [
                                            {"name": "Fz", "type": "eeg"},
                                            {"name": "Cz", "type": "eeg"},
                                        ],
                                        "events": [],
                                        "annotations": [],
                                        "decisions": [],
                                        "acquisition_metadata": {},
                                        "preprocessing_state": {},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "event_definitions": {},
        "channel_definitions": {},
        "plan_ids": [],
        "artifact_ids": [],
        "experiment_ids": [],
    }
    (study_dir / "study.json").write_text(json.dumps(raw), encoding="utf-8")

    study, streams = migrate_study_dict(raw)
    assert study.schema_version == 2
    assert len(streams) == 1
    assert streams[0].modality == Modality.EEG
    assert len(streams[0].channels) == 2
    assert study.subjects[0].sessions[0].runs[0].recordings[0].stream_ids == [
        streams[0].id
    ]

    # Repository auto-migrates on get
    loaded = repo.get_study(study_id)
    assert loaded.schema_version == 2
    listed = repo.list_streams(study_id)
    assert len(listed) == 1
    assert listed[0].modality == Modality.EEG
    ipc_streams = streams_list(StreamListParams(study_id=study_id), AppContext(tmp_path))
    assert len(ipc_streams["streams"]) == 1


def test_recommend_templates_returns_implemented_baselines() -> None:
    rec = recommend_templates()
    assert rec["recommendations"]
    assert rec["recommendations"][0]["template_id"] == "research_auto"
    assert rec["recommendations"][0].get("status") == "ready"
    assert "small labeled EEG" in (rec.get("explanation") or "")

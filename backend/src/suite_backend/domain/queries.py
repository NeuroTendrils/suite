from __future__ import annotations

from suite_backend.domain.models import DataStream, Recording, Run, Session, Study, Subject


def find_subject(study: Study, subject_id: str) -> Subject:
    for subject in study.subjects:
        if subject.id == subject_id:
            return subject
    raise KeyError(f"subject not found: {subject_id}")


def find_session(study: Study, subject_id: str, session_id: str) -> Session:
    subject = find_subject(study, subject_id)
    for session in subject.sessions:
        if session.id == session_id:
            return session
    raise KeyError(f"session not found: {session_id}")


def find_run(study: Study, subject_id: str, session_id: str, run_id: str) -> Run:
    session = find_session(study, subject_id, session_id)
    for run in session.runs:
        if run.id == run_id:
            return run
    raise KeyError(f"run not found: {run_id}")


def find_recording(study: Study, recording_id: str) -> Recording:
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for recording in run.recordings:
                    if recording.id == recording_id:
                        return recording
    raise KeyError(f"recording not found: {recording_id}")


def find_recording_in_subject(study: Study, subject_id: str, recording_id: str) -> Recording:
    """Subject-scoped lookup — prevents accidental cross-subject access."""
    subject = find_subject(study, subject_id)
    for session in subject.sessions:
        for run in session.runs:
            for recording in run.recordings:
                if recording.id == recording_id:
                    return recording
    raise KeyError(f"recording {recording_id} not found under subject {subject_id}")


def iter_recordings(study: Study):
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for recording in run.recordings:
                    yield subject, session, run, recording


def study_tree_summary(study: Study, streams: list[DataStream] | None = None) -> dict:
    streams = streams or []
    by_recording: dict[str, list[DataStream]] = {}
    for s in streams:
        by_recording.setdefault(s.recording_id, []).append(s)

    subjects_out = []
    for subject in study.subjects:
        sessions_out = []
        for session in subject.sessions:
            runs_out = []
            for run in session.runs:
                recs_out = []
                for rec in run.recordings:
                    rec_streams = by_recording.get(rec.id, [])
                    recs_out.append(
                        {
                            "id": rec.id,
                            "name": rec.name,
                            "source_format": rec.source_format,
                            "sampling_rate": rec.sampling_rate,
                            "channel_count": rec.channel_count,
                            "duration": rec.duration,
                            "stream_ids": list(rec.stream_ids),
                            "modalities": [s.modality.value for s in rec_streams],
                            "preprocessing_state": rec.preprocessing_state,
                        }
                    )
                runs_out.append(
                    {
                        "id": run.id,
                        "name": run.name,
                        "recordings": recs_out,
                        "metadata": run.metadata,
                    }
                )
            sessions_out.append(
                {
                    "id": session.id,
                    "name": session.name,
                    "runs": runs_out,
                    "metadata": session.metadata,
                }
            )
        subjects_out.append(
            {
                "id": subject.id,
                "label": subject.label,
                "metadata": subject.metadata,
                "sessions": sessions_out,
            }
        )
    return {
        "study_id": study.id,
        "schema_version": study.schema_version,
        "name": study.name,
        "task_name": study.task_name,
        "subjects": subjects_out,
        "stream_count": len(streams),
    }

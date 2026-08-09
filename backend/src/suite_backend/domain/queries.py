from __future__ import annotations

from suite_backend.domain.models import Recording, Study


def find_recording(study: Study, recording_id: str) -> Recording:
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for recording in run.recordings:
                    if recording.id == recording_id:
                        return recording
    raise KeyError(f"recording not found: {recording_id}")


def iter_recordings(study: Study):
    for subject in study.subjects:
        for session in subject.sessions:
            for run in session.runs:
                for recording in run.recordings:
                    yield subject, session, run, recording

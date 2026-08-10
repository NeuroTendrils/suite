"""Point EEG stream sample_paths at a derived FIF without mutating source files."""

from __future__ import annotations

from suite_backend.app_context import AppContext
from suite_backend.domain.models import Modality


def promote_working_fif(
    ctx: AppContext,
    *,
    study_id: str,
    recording_id: str,
    fif_path: str,
) -> list[str]:
    """Set working FIF on primary EEG streams; preserve prior under fif_original once."""
    updated: list[str] = []
    for stream in ctx.studies.list_streams(study_id, recording_id=recording_id):
        if stream.modality != Modality.EEG:
            continue
        paths = dict(stream.sample_paths or {})
        prev = paths.get("fif")
        if prev and prev != fif_path and "fif_original" not in paths:
            paths["fif_original"] = prev
        paths["fif"] = fif_path
        stream.sample_paths = paths
        ctx.studies.save_stream(study_id, stream)
        updated.append(stream.id)
    return updated

"""Dataset import / studio path selection."""

from __future__ import annotations

import shutil
from pathlib import Path

from neurotendrils.core.eeg_formats import (
    IMPORT_SUFFIXES,
    STUDIO_SUFFIXES,
    matches_suffix,
)
from neurotendrils.core.naming import sanitize_base_name, unique_path
from neurotendrils.core.projectdir import ProjectDir


def import_recording(source_path: str) -> tuple[str, bool]:
    """Copy into datasets/ if needed. Returns (path, copied)."""
    project = ProjectDir.instance()
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Recording not found: {source}")
    if not matches_suffix(str(source), IMPORT_SUFFIXES):
        raise ValueError("Unsupported EEG format")

    if project.contains(source):
        return str(source), False

    stem = sanitize_base_name(source.stem, "recording")
    # Preserve compound suffixes like .fif.gz
    name = source.name
    lower = name.lower()
    suffix = ""
    for s in IMPORT_SUFFIXES:
        if lower.endswith("." + s):
            suffix = "." + s
            break
    if not suffix:
        suffix = source.suffix

    dest = unique_path(project.datasets_dir(), stem, suffix)
    shutil.copy2(source, dest)
    return str(dest.resolve()), True


def select_studio_path(path: str) -> tuple[str, str]:
    """Return (resolved_path, kind) where kind is run_output|dataset|project_file."""
    project = ProjectDir.instance()
    p = Path(path).expanduser().resolve()
    if p.is_dir():
        cleaned = p / "cleaned.fif"
        if cleaned.is_file():
            p = cleaned
        else:
            raise FileNotFoundError("Directory has no cleaned.fif")

    if not p.is_file():
        raise FileNotFoundError(f"Training data not found: {p}")
    if not matches_suffix(str(p), STUDIO_SUFFIXES):
        raise ValueError("Unsupported training data format")
    if not project.contains(p):
        raise PermissionError("Training data must be inside the project folder")

    runs = project.runs_dir().resolve()
    datasets = project.datasets_dir().resolve()
    try:
        p.relative_to(runs)
        return str(p), "run_output"
    except ValueError:
        pass
    try:
        p.relative_to(datasets)
        return str(p), "dataset"
    except ValueError:
        return str(p), "project_file"

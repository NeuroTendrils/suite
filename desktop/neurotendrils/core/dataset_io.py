"""Dataset import / studio path selection."""

from __future__ import annotations

import shutil
from pathlib import Path

from neurotendrils.core.eeg_formats import (
    IMPORT_SUFFIXES,
    STUDIO_SUFFIXES,
    matched_suffix,
    matches_suffix,
)
from neurotendrils.core.naming import sanitize_base_name, unique_path
from neurotendrils.core.projectdir import ProjectDir

# Primary suffix → companion suffixes that must travel with it.
_COMPANIONS: dict[str, tuple[str, ...]] = {
    "vhdr": ("eeg", "vmrk"),
    "eeg": ("vhdr", "vmrk"),
    "set": ("fdt",),
}


def _companion_sources(source: Path, primary_suffix: str) -> list[Path]:
    extras: list[Path] = []
    for ext in _COMPANIONS.get(primary_suffix, ()):
        candidate = source.with_suffix("." + ext)
        # BrainVision uses .vhdr/.eeg/.vmrk with the same stem.
        if not candidate.is_file() and primary_suffix in {"vhdr", "eeg"}:
            candidate = source.parent / f"{source.stem}.{ext}"
        if candidate.is_file() and candidate != source:
            extras.append(candidate)
    # EEGLAB .set may sit beside stem.fdt
    if primary_suffix == "set":
        fdt = source.with_suffix(".fdt")
        if fdt.is_file():
            extras.append(fdt)
    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in extras:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def import_recording(
    source_path: str, *, project_root: str | None = None
) -> tuple[str, bool]:
    """Copy into datasets/ if needed. Returns (path, copied).

    *project_root* should be passed from the GUI thread when called from a
    worker so we do not touch the ProjectDir QObject off-thread.
    """
    root = project_root if project_root is not None else ProjectDir.instance().root
    if not root:
        raise RuntimeError("Project folder is not set")
    datasets_dir = Path(root) / "datasets"
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Recording not found: {source}")
    if not matches_suffix(str(source), IMPORT_SUFFIXES):
        raise ValueError("Unsupported EEG format")

    matched = matched_suffix(str(source), IMPORT_SUFFIXES) or source.suffix.lstrip(".")

    # Numeric .txt → FIF so fingerprint / Flow / viewer use MNE-native IO.
    if matched == "txt":
        from neurotendrils.core.ingestion.readers import read_recording

        stem = sanitize_base_name(source.stem, "recording")
        dest = unique_path(datasets_dir, stem, ".fif")
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = read_recording(source, preload=True)
        raw.save(str(dest), overwrite=True, verbose="ERROR")
        return str(dest.resolve()), True

    try:
        source.relative_to(Path(root).resolve())
        return str(source), False
    except ValueError:
        pass

    stem = sanitize_base_name(source.stem, "recording")
    suffix = f".{matched}" if matched else source.suffix

    dest = unique_path(datasets_dir, stem, suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)

    # Copy format companions next to the primary file (same dest stem).
    for companion in _companion_sources(source, matched):
        dest_extra = dest.with_name(dest.stem + companion.suffix)
        if not dest_extra.exists():
            shutil.copy2(companion, dest_extra)

    return str(dest.resolve()), True


def select_studio_path(path: str) -> tuple[str, str]:
    """Return (resolved_path, kind) where kind is run_output|dataset|dataset_manifest|project_file."""
    from neurotendrils.core.dataset_manifest import is_dataset_manifest, manifest_path_for

    project = ProjectDir.instance()
    p = Path(path).expanduser().resolve()
    if is_dataset_manifest(p):
        manifest = manifest_path_for(p)
        project.require_contains(manifest, "Training data")
        return str(manifest.resolve()), "dataset_manifest"

    if p.is_dir():
        for name in ("cleaned-epo.fif", "cleaned_epo.fif", "cleaned.fif"):
            candidate = p / name
            if candidate.is_file():
                p = candidate
                break
        else:
            raise FileNotFoundError("Directory has no cleaned.fif / cleaned-epo.fif")

    if not p.is_file():
        raise FileNotFoundError(f"Training data not found: {p}")
    if not matches_suffix(str(p), STUDIO_SUFFIXES):
        raise ValueError("Unsupported training data format")
    project.require_contains(p, "Training data")

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

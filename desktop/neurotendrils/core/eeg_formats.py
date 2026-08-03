"""Single source of truth for supported EEG file suffixes and dialog filters."""

from __future__ import annotations

# Full import list used by NeuroFlow and Hub indexing.
IMPORT_SUFFIXES: tuple[str, ...] = (
    "edf",
    "bdf",
    "fif",
    "fif.gz",
    "set",
    "vhdr",
    "eeg",
    "cnt",
    "mff",
    "gdf",
)

# NeuroStudio training inputs (cleaned / common formats).
STUDIO_SUFFIXES: tuple[str, ...] = (
    "fif",
    "fif.gz",
    "edf",
    "bdf",
    "set",
    "gdf",
)


def _filter_string(suffixes: tuple[str, ...], label: str) -> str:
    patterns = " ".join(f"*.{s}" for s in suffixes)
    return f"{label} ({patterns})"


def import_file_filter() -> str:
    return (
        f"{_filter_string(IMPORT_SUFFIXES, 'EEG recordings')};;"
        "All files (*)"
    )


def studio_file_filter() -> str:
    return (
        f"{_filter_string(STUDIO_SUFFIXES, 'Training data')};;"
        "All files (*)"
    )


def matches_suffix(path: str, suffixes: tuple[str, ...]) -> bool:
    lower = path.lower()
    for suffix in suffixes:
        if lower.endswith("." + suffix):
            return True
    return False


def extension_badge(path: str) -> str:
    lower = path.lower()
    for suffix in IMPORT_SUFFIXES:
        if lower.endswith("." + suffix):
            return suffix.upper()
    from pathlib import Path

    return Path(path).suffix.lstrip(".").upper() or "FILE"

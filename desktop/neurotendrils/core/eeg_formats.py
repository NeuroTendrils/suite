"""Single source of truth for supported EEG file suffixes and dialog filters."""

from __future__ import annotations

from pathlib import Path

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
    "txt",
)

STUDIO_SUFFIXES: tuple[str, ...] = (
    "fif",
    "fif.gz",
    "edf",
    "bdf",
    "set",
    "gdf",
    "txt",
)

# Sources that can be normalized into a multi-file dataset.
LAB_DATASET_SUFFIXES: tuple[str, ...] = (
    "fif",
    "fif.gz",
    "edf",
    "bdf",
    "set",
    "gdf",
    "mat",
    "txt",
)

_IMPORT_HINT_LABELS: dict[str, str | None] = {
    "edf": "EDF",
    "bdf": "BDF",
    "fif": "FIF",
    "fif.gz": None,  # covered by FIF
    "set": "EEGLAB SET",
    "vhdr": "BrainVision",
    "eeg": None,  # BrainVision companion
    "cnt": "CNT",
    "mff": "MFF",
    "gdf": "GDF",
    "txt": "TXT",
}


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


def lab_dataset_file_filter() -> str:
    return (
        f"{_filter_string(LAB_DATASET_SUFFIXES, 'Lab EEG sources')};;"
        "All files (*)"
    )


def import_format_hint() -> str:
    parts = [
        label
        for suffix in IMPORT_SUFFIXES
        if (label := _IMPORT_HINT_LABELS.get(suffix, suffix.upper())) is not None
    ]
    return "Supported: " + ", ".join(parts) + "."


def matched_suffix(path: str, suffixes: tuple[str, ...] = IMPORT_SUFFIXES) -> str | None:
    lower = path.lower()
    for suffix in suffixes:
        if lower.endswith("." + suffix):
            return suffix
    return None


def matches_suffix(path: str, suffixes: tuple[str, ...]) -> bool:
    return matched_suffix(path, suffixes) is not None


def extension_badge(path: str) -> str:
    suffix = matched_suffix(path, IMPORT_SUFFIXES)
    if suffix:
        return suffix.upper()
    return Path(path).suffix.lstrip(".").upper() or "FILE"

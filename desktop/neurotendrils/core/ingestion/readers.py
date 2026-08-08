"""Thin readers that normalize common EEG formats to MNE Raw."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neurotendrils.core.eeg_formats import matched_suffix


class ReadError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def read_recording(path: str | Path, *, preload: bool = True) -> Any:
    """Load a recording via MNE; raises ReadError on failure."""
    import mne

    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise ReadError("file_not_found", f"file not found: {file_path}")

    suffix = matched_suffix(file_path) or file_path.suffix.lstrip(".").lower()
    try:
        if suffix in {"fif", "fif.gz"}:
            try:
                return mne.io.read_raw_fif(str(file_path), preload=preload, verbose="ERROR")
            except ValueError:
                # Epoched FIF masquerading as raw path.
                return mne.read_epochs(str(file_path), preload=preload, verbose="ERROR")
        if suffix == "edf":
            return mne.io.read_raw_edf(str(file_path), preload=preload, verbose="ERROR")
        if suffix == "bdf":
            return mne.io.read_raw_bdf(str(file_path), preload=preload, verbose="ERROR")
        if suffix == "set":
            return mne.io.read_raw_eeglab(str(file_path), preload=preload, verbose="ERROR")
        if suffix == "vhdr":
            return mne.io.read_raw_brainvision(
                str(file_path), preload=preload, verbose="ERROR"
            )
        if suffix == "cnt":
            return mne.io.read_raw_cnt(str(file_path), preload=preload, verbose="ERROR")
        if suffix == "gdf":
            return mne.io.read_raw_gdf(str(file_path), preload=preload, verbose="ERROR")
        # Generic fallback.
        return mne.io.read_raw(str(file_path), preload=preload, verbose="ERROR")
    except ReadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ReadError("read_failed", f"failed to read {file_path.name}: {exc}") from exc


def list_annotation_labels(raw: Any) -> list[str]:
    ann = getattr(raw, "annotations", None)
    if ann is None or len(ann) == 0:
        return []
    labels: dict[str, int] = {}
    for desc in ann.description:
        key = str(desc)
        if key.upper().startswith("BAD"):
            continue
        labels[key] = labels.get(key, 0) + 1
    return sorted(labels.keys())

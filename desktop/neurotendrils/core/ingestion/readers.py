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

    suffix = matched_suffix(str(file_path)) or file_path.suffix.lstrip(".").lower()
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
        if suffix == "txt":
            return _read_numeric_txt(file_path)
        # Generic fallback.
        return mne.io.read_raw(str(file_path), preload=preload, verbose="ERROR")
    except ReadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ReadError("read_failed", f"failed to read {file_path.name}: {exc}") from exc


def _read_numeric_txt(path: Path, *, sfreq: float = 500.0, n_eeg: int = 32) -> Any:
    """Load comma/whitespace numeric matrix (rows=time) as MNE Raw."""
    import mne
    import numpy as np

    try:
        arr = np.loadtxt(path, delimiter=",", dtype=np.float64)
    except ValueError:
        arr = np.loadtxt(path, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    n_cols = int(arr.shape[1])
    eeg_cols = min(n_eeg, n_cols)
    data = arr[:, :eeg_cols].T
    # Lab TXT is often µV; MNE expects Volts. Convert when magnitude looks like µV.
    peak = float(np.nanmax(np.abs(data))) if data.size else 0.0
    if peak > 1.0:  # clearly not already in volts
        data = data * 1e-6
    ch_names = [f"EEG{i+1:02d}" for i in range(eeg_cols)]
    info = mne.create_info(ch_names, sfreq=float(sfreq), ch_types="eeg")
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    if n_cols >= eeg_cols + 1:
        marker = arr[:, -1]
        onsets: list[float] = []
        descriptions: list[str] = []
        prev = None
        for i, val in enumerate(marker):
            v = float(val)
            if v == 0 or (prev is not None and v == prev):
                prev = v
                continue
            onsets.append(i / float(sfreq))
            descriptions.append(f"mark_{int(v)}" if v == int(v) else f"mark_{v}")
            prev = v
        if onsets:
            raw.set_annotations(
                mne.Annotations(onsets, [0.0] * len(onsets), descriptions)
            )
    return raw


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

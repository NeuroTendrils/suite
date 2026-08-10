"""Content-aware MAT inspection/import — never silently guess layout."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.domain.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    DatasetArtifact,
    Recording,
)

_SKIP_KEYS = {"__header__", "__version__", "__globals__", "__function_workspace__"}


def _load_mat(path: Path) -> dict[str, Any]:
    try:
        from scipy.io import loadmat
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("scipy is required for .mat import") from exc
    try:
        return loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except NotImplementedError as exc:
        # MATLAB v7.3 (HDF5)
        raise ValueError(
            "MATLAB v7.3 HDF5 .mat is not supported yet; save as v7 or export arrays"
        ) from exc


def _array_candidates(mat: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, value in mat.items():
        if key in _SKIP_KEYS:
            continue
        arr = np.asanyarray(value)
        if arr.dtype == object:
            continue
        if arr.ndim < 1 or arr.size == 0:
            continue
        if not np.issubdtype(arr.dtype, np.number):
            continue
        out.append(
            {
                "key": key,
                "shape": list(arr.shape),
                "dtype": str(arr.dtype),
                "ndim": int(arr.ndim),
            }
        )
    # Prefer larger 2D arrays first
    out.sort(key=lambda c: (-(c["ndim"] >= 2), -int(np.prod(c["shape"])), c["key"]))
    return out


def inspect_mat(source: str | Path) -> dict[str, Any]:
    path = Path(source).expanduser().resolve()
    try:
        mat = _load_mat(path)
    except Exception as exc:  # noqa: BLE001
        return {
            "format": "mat",
            "path": str(path),
            "status": "unreadable",
            "self_describing": False,
            "required_config": ["data_key", "sfreq"],
            "error": str(exc),
            "warnings": [str(exc)],
        }

    candidates = _array_candidates(mat)
    warnings = [
        "MAT files are ambiguous: choose data_key and sfreq explicitly — nothing is guessed on import"
    ]
    if not candidates:
        warnings.append("no numeric array candidates found")

    suggested = candidates[0]["key"] if candidates else None
    return {
        "format": "mat",
        "path": str(path),
        "status": "needs_config",
        "self_describing": False,
        "required_config": ["data_key", "sfreq"],
        "optional_config": ["transpose", "channel_names", "montage"],
        "candidates": candidates,
        "suggested_data_key": suggested,
        "file_size_bytes": path.stat().st_size,
        "warnings": warnings,
        "config_schema": {
            "data_key": "name of numeric array in the .mat file",
            "sfreq": "sampling rate in Hz (required; not inferred)",
            "transpose": "if true, treat rows as channels",
        },
    }


def import_mat_recording(
    source: str | Path,
    *,
    subject_id: str,
    session_id: str,
    run_id: str,
    data_key: str,
    sfreq: float,
    transpose: bool = False,
    channel_names: list[str] | None = None,
    montage: str | None = None,
    artifact_dir: Path | None = None,
) -> tuple[Recording, DatasetArtifact, Any]:
    import mne

    if not data_key:
        raise ValueError("MAT import requires data_key (array variable name)")
    if sfreq is None or float(sfreq) <= 0:
        raise ValueError("MAT import requires sfreq > 0 (Hz) — not inferred from file")

    path = Path(source).expanduser().resolve()
    mat = _load_mat(path)
    if data_key not in mat:
        raise KeyError(f"data_key {data_key!r} not in MAT file; keys={list(mat)}")

    data = np.asanyarray(mat[data_key], dtype=np.float64)
    if data.ndim == 1:
        data = data.reshape(1, -1) if transpose else data.reshape(-1, 1)
    if data.ndim != 2:
        raise ValueError(f"MAT array {data_key!r} must be 2D after squeeze; got shape {data.shape}")

    # Default: rows=samples, cols=channels (same as text_matrix)
    data_ch_time = data if transpose else data.T
    n_ch, n_times = data_ch_time.shape
    if channel_names and len(channel_names) == n_ch:
        ch_names = [str(n) for n in channel_names]
    else:
        ch_names = [f"ch{i + 1:03d}" for i in range(n_ch)]

    info = mne.create_info(ch_names=ch_names, sfreq=float(sfreq), ch_types="eeg")
    raw = mne.io.RawArray(data_ch_time, info, verbose=False)
    if montage:
        from suite_backend.scientific.io.text_matrix import _apply_montage

        _apply_montage(raw, montage)

    fif_path: Path | None = None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        fif_path = artifact_dir / f"import_{path.stem}_raw.fif"
        raw.save(fif_path, overwrite=True, verbose=False)

    digest = hashlib.sha256(f"{path}:{data_key}:{sfreq}".encode()).hexdigest()
    channels = [
        Channel(name=n, type=ChannelType.EEG, status=ChannelStatus.UNKNOWN) for n in raw.ch_names
    ]
    recording = Recording(
        subject_id=subject_id,
        session_id=session_id,
        run_id=run_id,
        source_files=[str(fif_path)] if fif_path else [str(path)],
        source_format="mat",
        sampling_rate=float(raw.info["sfreq"]),
        duration=float(raw.n_times / raw.info["sfreq"]),
        channel_count=len(channels),
        channels=channels,
        acquisition_metadata={
            "original_path": str(path),
            "data_key": data_key,
            "transpose": transpose,
            "n_times": int(n_times),
        },
    )
    artifact = DatasetArtifact(
        type="raw_recording",
        operation="import_mat",
        parameters={
            "format": "mat",
            "source": str(path),
            "data_key": data_key,
            "sfreq": float(sfreq),
            "transpose": transpose,
            "montage": montage,
        },
        checksum=digest,
        paths={
            "source": str(path),
            **({"fif": str(fif_path)} if fif_path else {}),
        },
        recording_id=recording.id,
    )
    recording.artifact_id = artifact.id
    return recording, artifact, raw

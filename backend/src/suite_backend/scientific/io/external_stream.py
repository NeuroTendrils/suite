"""Import non-EEG modalities as independent DataStreams.

Same contract as ambiguous EEG text/MAT: inspect → explicit config → import.
Never assume modality or sampling rate from filename alone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import numpy as np

from suite_backend.domain.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    DataStream,
    DatasetArtifact,
    Modality,
)

MODALITY_UNITS = {
    Modality.GYRO: "deg/s",
    Modality.ACCEL: "m/s^2",
    Modality.ECG: "mV",
    Modality.EMG: "uV",
    Modality.EOG: "uV",
    Modality.EYE_TRACKING: "px",
    Modality.MOTION: "a.u.",
    Modality.BEHAVIORAL: "a.u.",
    Modality.TRIGGER: "a.u.",
    Modality.GSR: "uS",
    Modality.RESPIRATION: "a.u.",
    Modality.MISC: "a.u.",
}

_CHANNEL_TYPE_FOR_MODALITY = {
    Modality.GYRO: ChannelType.GYRO,
    Modality.ACCEL: ChannelType.ACCEL,
    Modality.ECG: ChannelType.ECG,
    Modality.EMG: ChannelType.EMG,
    Modality.EOG: ChannelType.EOG,
    Modality.EYE_TRACKING: ChannelType.EYE_TRACKING,
    Modality.TRIGGER: ChannelType.TRIGGER,
    Modality.GSR: ChannelType.GSR,
    Modality.RESPIRATION: ChannelType.RESPIRATION,
    Modality.MOTION: ChannelType.MISC,
    Modality.BEHAVIORAL: ChannelType.MISC,
    Modality.MISC: ChannelType.MISC,
}


def parse_modality(value: str | Modality) -> Modality:
    if isinstance(value, Modality):
        return value
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "gyro": Modality.GYRO,
        "gyroscope": Modality.GYRO,
        "accel": Modality.ACCEL,
        "accelerometer": Modality.ACCEL,
        "acc": Modality.ACCEL,
        "ecg": Modality.ECG,
        "emg": Modality.EMG,
        "eog": Modality.EOG,
        "eye": Modality.EYE_TRACKING,
        "eye_tracking": Modality.EYE_TRACKING,
        "eyetracking": Modality.EYE_TRACKING,
        "motion": Modality.MOTION,
        "mocap": Modality.MOTION,
        "behavioral": Modality.BEHAVIORAL,
        "behavioural": Modality.BEHAVIORAL,
        "behavior": Modality.BEHAVIORAL,
        "trigger": Modality.TRIGGER,
        "gsr": Modality.GSR,
        "eda": Modality.GSR,
        "resp": Modality.RESPIRATION,
        "respiration": Modality.RESPIRATION,
        "misc": Modality.MISC,
    }
    if key in aliases:
        return aliases[key]
    return Modality(key)


def suggest_modality_from_path(path: Path) -> str | None:
    name = path.stem.lower()
    for token, mod in [
        ("gyro", "gyroscope"),
        ("accel", "accelerometer"),
        ("acc_", "accelerometer"),
        ("ecg", "ecg"),
        ("emg", "emg"),
        ("eog", "eog"),
        ("eye", "eye_tracking"),
        ("gaze", "eye_tracking"),
        ("motion", "motion"),
        ("mocap", "motion"),
        ("behav", "behavioral"),
        ("marker", "trigger"),
        ("stim", "trigger"),
    ]:
        if token in name:
            return mod
    return None


def inspect_external_source(source: str | Path) -> dict[str, Any]:
    """Inspect a file as a potential external modality stream."""
    path = Path(source).expanduser().resolve()
    suffix = path.suffix.lower()
    suggested = suggest_modality_from_path(path)

    base = {
        "path": str(path),
        "self_describing": False,
        "status": "needs_config",
        "required_config": ["modality", "sfreq"],
        "optional_config": [
            "units",
            "column_selection",
            "transpose",
            "channel_names",
            "timestamp_column",
            "name",
        ],
        "suggested_modality": suggested,
        "warnings": [
            "External modalities require explicit modality + sampling rate (or timestamp_column)",
            "Modality is never inferred at import time — suggested_modality is a hint only",
        ],
    }

    if suffix in {".txt", ".csv", ".tsv", ".asc"}:
        from suite_backend.scientific.io.text_matrix import inspect_text_matrix

        text = inspect_text_matrix(path)
        return {
            **base,
            "format": "external_text",
            "n_rows": text.get("n_rows"),
            "n_cols": text.get("n_cols"),
            "columns": text.get("columns"),
            "preview": text.get("preview"),
            "delimiter": text.get("delimiter"),
            "file_size_bytes": text.get("file_size_bytes"),
            "warnings": base["warnings"] + list(text.get("warnings") or []),
        }

    if suffix == ".mat":
        from suite_backend.scientific.io.mat_import import inspect_mat

        mat = inspect_mat(path)
        return {
            **base,
            "format": "external_mat",
            "required_config": ["modality", "data_key", "sfreq"],
            "candidates": mat.get("candidates"),
            "suggested_data_key": mat.get("suggested_data_key"),
            "file_size_bytes": mat.get("file_size_bytes"),
            "warnings": base["warnings"] + list(mat.get("warnings") or []),
        }

    if suffix == ".npy":
        arr = np.load(path, mmap_mode="r")
        return {
            **base,
            "format": "external_npy",
            "shape": list(arr.shape),
            "dtype": str(arr.dtype),
            "file_size_bytes": path.stat().st_size,
        }

    return {
        **base,
        "format": "external_unknown",
        "status": "unreadable",
        "error": f"unsupported external modality extension: {suffix}",
        "warnings": base["warnings"] + [f"unsupported extension {suffix}"],
    }


def _load_numeric_matrix(
    path: Path,
    *,
    data_key: str | None,
    transpose: bool,
    column_selection: Sequence[dict[str, Any]] | None,
    include_columns: Sequence[int] | None,
    channel_names: list[str] | None,
    timestamp_column: int | None,
) -> tuple[np.ndarray, list[str], np.ndarray | None]:
    """Return data (n_channels, n_times), channel names, optional timestamps."""
    suffix = path.suffix.lower()
    times: np.ndarray | None = None

    if suffix == ".npy":
        data = np.asanyarray(np.load(path), dtype=np.float64)
        if data.ndim == 1:
            data = data.reshape(1, -1) if transpose else data.reshape(-1, 1)
        data_ch_time = data if transpose else data.T
        names = channel_names or [f"ch{i + 1:03d}" for i in range(data_ch_time.shape[0])]
        return data_ch_time, names, None

    if suffix == ".mat":
        from suite_backend.scientific.io.mat_import import _load_mat

        if not data_key:
            raise ValueError("MAT external import requires data_key")
        mat = _load_mat(path)
        data = np.asanyarray(mat[data_key], dtype=np.float64)
        if data.ndim == 1:
            data = data.reshape(1, -1) if transpose else data.reshape(-1, 1)
        data_ch_time = data if transpose else data.T
        names = channel_names or [f"ch{i + 1:03d}" for i in range(data_ch_time.shape[0])]
        return data_ch_time, names, None

    # text / csv / tsv
    from suite_backend.scientific.io import text_matrix as tm

    sniffed = tm._sniff_structure(path, max_preview_rows=2)
    n_cols = int(sniffed["n_cols"])
    selection = tm._normalize_column_selection(
        n_cols, column_selection, channel_names, include_columns, header=sniffed["header"]
    )

    ts_col = timestamp_column
    keep: list[dict[str, Any]] = []
    for c in selection:
        if ts_col is not None and c["index"] == ts_col:
            continue
        if c["role"] == tm.ROLE_IGNORE:
            continue
        if c["role"] == tm.ROLE_TIME:
            if ts_col is None:
                ts_col = c["index"]
            continue
        keep.append(c)
    if not keep:
        raise ValueError("no signal columns selected for external stream")

    usecols = [c["index"] for c in keep]
    usecols_with_ts = sorted(set(usecols + ([ts_col] if ts_col is not None else [])))
    kw = tm._loadtxt_kwargs(sniffed["delimiter"], int(sniffed["data_start"]), usecols_with_ts)
    loaded = np.loadtxt(path, **kw)
    if loaded.ndim == 1:
        loaded = loaded.reshape(-1, 1)

    col_to_pos = {col: i for i, col in enumerate(usecols_with_ts)}
    if ts_col is not None:
        times = loaded[:, col_to_pos[ts_col]].astype(np.float64)
    # samples × channels
    signal_sc = np.column_stack([loaded[:, col_to_pos[c["index"]]] for c in keep])
    # channels × samples
    data_ch_time = signal_sc if transpose else signal_sc.T
    if transpose and data_ch_time.shape[0] != len(keep) and data_ch_time.shape[1] == len(keep):
        data_ch_time = data_ch_time.T

    names = (
        list(channel_names)
        if channel_names and len(channel_names) == data_ch_time.shape[0]
        else [c["name"] for c in keep]
    )
    return np.asarray(data_ch_time, dtype=np.float64), names, times


def import_external_stream(
    source: str | Path,
    *,
    study_id: str,
    recording_id: str,
    subject_id: str,
    session_id: str,
    run_id: str,
    modality: str | Modality,
    sfreq: float | None,
    units: str | None = None,
    name: str | None = None,
    data_key: str | None = None,
    transpose: bool = False,
    channel_names: list[str] | None = None,
    include_columns: Sequence[int] | None = None,
    column_selection: Sequence[dict[str, Any]] | None = None,
    timestamp_column: int | None = None,
    sample_dir: Path | None = None,
) -> tuple[DataStream, DatasetArtifact]:
    path = Path(source).expanduser().resolve()
    mod = parse_modality(modality)

    if sfreq is None and timestamp_column is None:
        # Also allow time-role columns inside column_selection
        has_time_role = any(
            str(c.get("role")) == "time" for c in (column_selection or [])
        )
        if not has_time_role:
            raise ValueError(
                "external stream import requires sfreq (Hz) or timestamp_column — not guessed"
            )

    data_ch_time, names, times = _load_numeric_matrix(
        path,
        data_key=data_key,
        transpose=transpose,
        column_selection=column_selection,
        include_columns=include_columns,
        channel_names=channel_names,
        timestamp_column=timestamp_column,
    )
    n_ch, n_times = data_ch_time.shape

    resolved_sfreq = float(sfreq) if sfreq is not None else None
    if resolved_sfreq is None and times is not None and len(times) > 1:
        dt = np.diff(times)
        dt = dt[dt > 0]
        if dt.size:
            resolved_sfreq = float(1.0 / np.median(dt))
    if resolved_sfreq is None or resolved_sfreq <= 0:
        raise ValueError("could not determine sfreq; provide sfreq explicitly")

    duration = float(n_times / resolved_sfreq)
    if times is not None and len(times) > 1:
        duration = float(times[-1] - times[0])

    ch_type = _CHANNEL_TYPE_FOR_MODALITY.get(mod, ChannelType.MISC)
    unit = units or MODALITY_UNITS.get(mod, "a.u.")
    channels = [
        Channel(name=n, type=ch_type, unit=unit, status=ChannelStatus.UNKNOWN) for n in names
    ]

    stream = DataStream(
        recording_id=recording_id,
        subject_id=subject_id,
        session_id=session_id,
        run_id=run_id,
        modality=mod,
        name=name or mod.value,
        source_files=[str(path)],
        source_format=path.suffix.lower().lstrip(".") or "external",
        sampling_rate=resolved_sfreq,
        duration=duration,
        n_samples=int(n_times),
        channels=channels,
        units=unit,
        acquisition_metadata={
            "original_path": str(path),
            "data_key": data_key,
            "transpose": transpose,
            "timestamp_column": timestamp_column,
        },
        provenance={"created_by": "import.stream", "modality": mod.value},
    )

    sample_paths: dict[str, str] = {}
    if sample_dir is not None:
        sample_dir.mkdir(parents=True, exist_ok=True)
        data_path = sample_dir / f"{stream.id}_data.npy"
        np.save(data_path, data_ch_time)
        sample_paths["data_npy"] = str(data_path)
        if times is not None:
            t_path = sample_dir / f"{stream.id}_times.npy"
            np.save(t_path, times.astype(np.float64))
            sample_paths["times_npy"] = str(t_path)
            stream.timestamp_path = str(t_path)
    stream.sample_paths = sample_paths

    artifact = DatasetArtifact(
        type="raw_stream",
        operation="import_external_stream",
        parameters={
            "modality": mod.value,
            "source": str(path),
            "sfreq": resolved_sfreq,
            "units": unit,
            "data_key": data_key,
            "transpose": transpose,
            "timestamp_column": timestamp_column,
        },
        paths={"source": str(path), **sample_paths},
        recording_id=recording_id,
        stream_id=stream.id,
        study_id=study_id,
        checksum=None,
    )
    stream.artifact_id = artifact.id
    return stream, artifact

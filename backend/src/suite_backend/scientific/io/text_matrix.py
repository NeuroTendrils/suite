"""Content-aware import for numeric EEG matrices in .txt / .csv / .tsv."""

from __future__ import annotations

import hashlib
import re
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


def _sniff_delimiter(sample_lines: list[str]) -> str:
    scores = {"\t": 0, ",": 0, ";": 0, r"\s+": 0}
    for line in sample_lines:
        if not line.strip() or line.lstrip().startswith(("#", "%", "//")):
            continue
        scores["\t"] += line.count("\t")
        scores[","] += line.count(",")
        scores[";"] += line.count(";")
        scores[r"\s+"] += len(re.findall(r"\s+", line.strip()))
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else r"\s+"


def _split_line(line: str, delimiter: str) -> list[str]:
    if delimiter == r"\s+":
        return line.strip().split()
    return [p.strip() for p in line.strip().split(delimiter)]


def _is_numeric_row(parts: list[str]) -> bool:
    if not parts:
        return False
    for p in parts:
        try:
            float(p)
        except ValueError:
            return False
    return True


def inspect_text_matrix(source: str | Path, *, max_preview_rows: int = 8) -> dict[str, Any]:
    path = Path(source).expanduser().resolve()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    sample = non_empty[:50]
    delimiter = _sniff_delimiter(sample)

    header: list[str] | None = None
    data_start = 0
    skipped_comments = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "%", "//")):
            skipped_comments += 1
            continue
        parts = _split_line(stripped, delimiter)
        if not _is_numeric_row(parts):
            header = parts
            data_start = i + 1
        else:
            data_start = i
        break

    # Count numeric rows / cols without loading entire huge files into object arrays twice
    n_rows = 0
    n_cols = 0
    preview: list[list[float]] = []
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "%", "//")):
            continue
        parts = _split_line(stripped, delimiter)
        if not _is_numeric_row(parts):
            continue
        n_cols = max(n_cols, len(parts))
        n_rows += 1
        if len(preview) < max_preview_rows:
            preview.append([float(x) for x in parts])

    warnings: list[str] = []
    if n_rows == 0 or n_cols == 0:
        warnings.append("no numeric matrix detected")
    if header and len(header) != n_cols:
        warnings.append(
            f"header has {len(header)} labels but matrix has {n_cols} columns"
        )
    warnings.append(
        "sampling rate is not in the file; you must provide sfreq_hz on import"
    )

    return {
        "format": "text_matrix",
        "path": str(path),
        "status": "ok" if n_rows and n_cols else "unreadable",
        "delimiter": "whitespace" if delimiter == r"\s+" else delimiter,
        "has_header": header is not None,
        "channel_names": header,
        "n_rows": n_rows,
        "n_cols": n_cols,
        "assumed_layout": "rows=samples, cols=channels",
        "skipped_comment_lines": skipped_comments,
        "preview": preview,
        "warnings": warnings,
    }


def load_text_matrix(
    source: str | Path,
    *,
    sfreq: float,
    transpose: bool = False,
    channel_names: list[str] | None = None,
) -> tuple[Any, dict[str, Any]]:
    """
    Load text matrix as MNE Raw.

    Default layout: rows = samples, columns = channels.
    Set transpose=True if rows = channels.
    """
    import mne

    if sfreq <= 0:
        raise ValueError("sfreq must be > 0 for text imports")

    path = Path(source).expanduser().resolve()
    meta = inspect_text_matrix(path)
    if meta["status"] != "ok":
        raise ValueError(f"cannot parse text matrix: {meta.get('warnings')}")

    delimiter = _sniff_delimiter(
        [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()][
            :50
        ]
    )
    # numpy load — skip non-numeric leading rows
    skip = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "%", "//")):
            skip += 1
            continue
        parts = _split_line(stripped, delimiter)
        if not _is_numeric_row(parts):
            skip += 1
            continue
        break

    if delimiter == r"\s+":
        data = np.loadtxt(path, dtype=float, comments=["#", "%"], skiprows=skip)
    elif delimiter == ",":
        data = np.loadtxt(path, dtype=float, delimiter=",", comments=["#", "%"], skiprows=skip)
    elif delimiter == ";":
        data = np.loadtxt(path, dtype=float, delimiter=";", comments=["#", "%"], skiprows=skip)
    else:
        data = np.loadtxt(path, dtype=float, delimiter="\t", comments=["#", "%"], skiprows=skip)

    if data.ndim == 1:
        data = data.reshape(-1, 1)

    if transpose:
        # rows were channels
        data_ch_time = data.astype(np.float64)
    else:
        # rows samples, cols channels → (n_channels, n_times)
        data_ch_time = data.T.astype(np.float64)

    n_ch, n_times = data_ch_time.shape
    names = channel_names or meta.get("channel_names")
    if names and len(names) == n_ch:
        ch_names = [str(n) for n in names]
    else:
        ch_names = [f"ch{i + 1:03d}" for i in range(n_ch)]

    info = mne.create_info(ch_names=ch_names, sfreq=float(sfreq), ch_types="eeg")
    raw = mne.io.RawArray(data_ch_time, info, verbose=False)
    meta_out = {
        **meta,
        "sfreq": float(sfreq),
        "transpose": transpose,
        "n_channels": n_ch,
        "n_times": n_times,
        "duration_sec": n_times / float(sfreq),
    }
    return raw, meta_out


def import_text_recording(
    source: str | Path,
    *,
    subject_id: str,
    session_id: str,
    run_id: str,
    sfreq: float,
    transpose: bool = False,
    channel_names: list[str] | None = None,
    artifact_dir: Path | None = None,
) -> tuple[Recording, DatasetArtifact, Any]:
    path = Path(source).expanduser().resolve()
    raw, meta = load_text_matrix(
        path, sfreq=sfreq, transpose=transpose, channel_names=channel_names
    )

    # Persist a FIF so the rest of the app can load via MNE like other formats.
    fif_path: Path | None = None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        fif_path = artifact_dir / f"import_{path.stem}.fif"
        raw.save(fif_path, overwrite=True, verbose=False)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    channels = [
        Channel(name=name, type=ChannelType.EEG, status=ChannelStatus.UNKNOWN)
        for name in raw.ch_names
    ]
    recording = Recording(
        subject_id=subject_id,
        session_id=session_id,
        run_id=run_id,
        source_files=[str(fif_path)] if fif_path else [str(path)],
        source_format="text_matrix",
        sampling_rate=float(raw.info["sfreq"]),
        duration=float(raw.n_times / raw.info["sfreq"]),
        channel_count=len(channels),
        channels=channels,
        acquisition_metadata={
            "original_path": str(path),
            "text_import": meta,
        },
    )
    artifact = DatasetArtifact(
        type="raw_recording",
        operation="import_text_matrix",
        parameters={
            "format": "text_matrix",
            "source": str(path),
            "sfreq": float(sfreq),
            "transpose": transpose,
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

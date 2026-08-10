"""Content-aware import for numeric EEG matrices in .txt / .csv / .tsv."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from suite_backend.domain.models import (
    Channel,
    ChannelLocation,
    ChannelStatus,
    ChannelType,
    DatasetArtifact,
    Recording,
)

ROLE_EEG = "eeg"
ROLE_STIM = "stim"
ROLE_MISC = "misc"
ROLE_IGNORE = "ignore"
ROLE_TIME = "time"
VALID_ROLES = {ROLE_EEG, ROLE_STIM, ROLE_MISC, ROLE_IGNORE, ROLE_TIME}

# Names that are usually not scalp EEG electrodes in export dumps.
_NON_EEG_NAME = re.compile(
    r"^(time|t|sample|samples|index|idx|marker|markers|trigger|stim|event|events|"
    r"label|counter|packet|seq|timestamp|ms|sec|seconds)$",
    re.I,
)

_BUILTIN_MONTAGES = (
    "standard_1020",
    "standard_1005",
    "biosemi16",
    "biosemi32",
    "biosemi64",
    "easycap-M1",
    "easycap-M10",
    "GSN-HydroCel-32",
    "GSN-HydroCel-64_1.0",
)


def list_montages() -> list[str]:
    try:
        import mne

        return list(mne.channels.get_builtin_montages())
    except Exception:
        return list(_BUILTIN_MONTAGES)


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


def _read_head_text(path: Path, max_bytes: int = 262_144) -> str:
    with path.open("rb") as fh:
        return fh.read(max_bytes).decode("utf-8", errors="replace")


def _count_data_rows(path: Path, data_start_line: int) -> int:
    """Count non-empty, non-comment lines after data_start (1-based skiprows style)."""
    n = 0
    with path.open("rb") as fh:
        for i, raw in enumerate(fh):
            if i < data_start_line:
                continue
            s = raw.lstrip()
            if not s or s.startswith((b"#", b"%", b"//")):
                continue
            n += 1
    return n


def _suggest_role(name: str | None, col_index: int, n_cols: int) -> str:
    del col_index, n_cols  # no fixed channel-count heuristics
    if name and _NON_EEG_NAME.match(name.strip()):
        if re.match(r"^(marker|markers|trigger|stim|event|events)$", name.strip(), re.I):
            return ROLE_STIM
        if re.match(r"^(time|t|timestamp|ms|sec|seconds)$", name.strip(), re.I):
            return ROLE_TIME
        return ROLE_IGNORE
    return ROLE_EEG


def _default_columns(n_cols: int, header: list[str] | None) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = []
    for i in range(n_cols):
        name = header[i] if header and i < len(header) else f"ch{i + 1:03d}"
        role = _suggest_role(header[i] if header and i < len(header) else None, i, n_cols)
        cols.append({"index": i, "name": str(name), "role": role})
    return cols


_MNE_RESERVED_NAMES = {
    "meg",
    "eeg",
    "stim",
    "eog",
    "ecg",
    "emg",
    "misc",
    "seeg",
    "dbs",
    "ecog",
    "bio",
    "chpi",
    "dipole",
    "gof",
    "all",
    "data",
}


def _safe_ch_name(name: str, idx: int) -> str:
    n = str(name).strip() or f"ch{idx + 1:03d}"
    if n.lower() in _MNE_RESERVED_NAMES:
        return f"{n}_ch"
    return n


def _normalize_column_selection(
    n_cols: int,
    column_selection: Sequence[dict[str, Any]] | None,
    channel_names: list[str] | None,
    include_columns: Sequence[int] | None,
    header: list[str] | None = None,
) -> list[dict[str, Any]]:
    if column_selection:
        out: list[dict[str, Any]] = []
        for item in column_selection:
            idx = int(item["index"])
            if idx < 0 or idx >= n_cols:
                raise ValueError(f"column index {idx} out of range 0..{n_cols - 1}")
            role = str(item.get("role", ROLE_EEG)).lower()
            if role not in VALID_ROLES:
                raise ValueError(f"invalid column role: {role}")
            name = _safe_ch_name(str(item.get("name") or f"ch{idx + 1:03d}"), idx)
            out.append({"index": idx, "name": name, "role": role})
        return sorted(out, key=lambda c: c["index"])

    base = _default_columns(n_cols, header)
    for c in base:
        c["name"] = _safe_ch_name(c["name"], c["index"])
    if include_columns is not None:
        keep = set(int(i) for i in include_columns)
        for c in base:
            c["role"] = ROLE_EEG if c["index"] in keep else ROLE_IGNORE
    if channel_names:
        eeg_idxs = [c["index"] for c in base if c["role"] == ROLE_EEG]
        if len(channel_names) == len(eeg_idxs):
            for name, idx in zip(channel_names, eeg_idxs):
                base[idx]["name"] = _safe_ch_name(str(name), idx)
        elif len(channel_names) == n_cols:
            for i, name in enumerate(channel_names):
                base[i]["name"] = _safe_ch_name(str(name), i)
    return base


def _role_to_channel_type(role: str) -> ChannelType:
    if role == ROLE_STIM:
        return ChannelType.TRIGGER
    if role == ROLE_MISC:
        return ChannelType.MISC
    return ChannelType.EEG


def _role_to_mne_type(role: str) -> str:
    if role == ROLE_STIM:
        return "stim"
    if role == ROLE_MISC:
        return "misc"
    return "eeg"


def _sniff_structure(
    path: Path, *, max_preview_rows: int = 8
) -> dict[str, Any]:
    size = path.stat().st_size
    head = _read_head_text(path)
    if size > len(head) and "\n" in head:
        head = head.rsplit("\n", 1)[0]

    lines = head.splitlines()
    non_empty = [ln for ln in lines if ln.strip()]
    delimiter = _sniff_delimiter(non_empty[:50])

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

    preview: list[list[float]] = []
    n_cols = 0
    for line in lines[data_start:]:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "%", "//")):
            continue
        parts = _split_line(stripped, delimiter)
        if not _is_numeric_row(parts):
            continue
        n_cols = max(n_cols, len(parts))
        if len(preview) < max_preview_rows:
            preview.append([float(x) for x in parts])
        if len(preview) >= max_preview_rows and n_cols:
            break

    return {
        "size": size,
        "delimiter": delimiter,
        "header": header,
        "data_start": data_start,
        "skipped_comments": skipped_comments,
        "n_cols": n_cols,
        "preview": preview,
    }


def inspect_text_matrix(source: str | Path, *, max_preview_rows: int = 8) -> dict[str, Any]:
    """
    Fast inspect for large files: only parses a head sample for shape/preview,
    then counts data rows with a single binary pass (no float parsing).
    """
    path = Path(source).expanduser().resolve()
    sniffed = _sniff_structure(path, max_preview_rows=max_preview_rows)
    n_cols = int(sniffed["n_cols"])
    data_start = int(sniffed["data_start"])
    header = sniffed["header"]
    size = int(sniffed["size"])
    delimiter = sniffed["delimiter"]

    n_rows = _count_data_rows(path, data_start) if n_cols else 0
    columns = _default_columns(n_cols, header)
    n_eeg = sum(1 for c in columns if c["role"] == ROLE_EEG)

    warnings: list[str] = []
    if n_rows == 0 or n_cols == 0:
        warnings.append("no numeric matrix detected")
    if header and len(header) != n_cols:
        warnings.append(f"header has {len(header)} labels but matrix has {n_cols} columns")
    warnings.append("sampling rate is not in the file; you must provide sfreq_hz on import")
    if n_cols > n_eeg:
        warnings.append(
            f"{n_cols} columns detected; {n_eeg} suggested as EEG — review column roles before import"
        )
    if size > 50_000_000:
        warnings.append(
            f"large file ({size / 1e9:.2f} GB): inspect is streamed; import still reads selected columns once"
        )

    return {
        "format": "text_matrix",
        "path": str(path),
        "status": "ok" if n_rows and n_cols else "unreadable",
        "delimiter": "whitespace" if delimiter == r"\s+" else delimiter,
        "has_header": header is not None,
        "channel_names": [c["name"] for c in columns if c["role"] == ROLE_EEG],
        "columns": columns,
        "n_rows": n_rows,
        "n_cols": n_cols,
        "file_size_bytes": size,
        "assumed_layout": "rows=samples, cols=channels (+ optional non-EEG columns)",
        "skipped_comment_lines": sniffed["skipped_comments"],
        "data_start_line": data_start,
        "preview": sniffed["preview"],
        "montages": list(_BUILTIN_MONTAGES),
        "warnings": warnings,
    }


def _loadtxt_kwargs(delimiter: str, skiprows: int, usecols: Sequence[int] | None) -> dict[str, Any]:
    kw: dict[str, Any] = {
        "dtype": np.float64,
        "comments": ("#", "%"),
        "skiprows": skiprows,
    }
    if usecols is not None:
        kw["usecols"] = tuple(usecols)
    if delimiter == r"\s+":
        pass
    elif delimiter == ",":
        kw["delimiter"] = ","
    elif delimiter == ";":
        kw["delimiter"] = ";"
    else:
        kw["delimiter"] = "\t"
    return kw


def _apply_montage(raw: Any, montage_name: str | None) -> dict[str, Any]:
    if not montage_name:
        return {"montage": None, "matched": 0, "missing": []}
    import mne

    montage = mne.channels.make_standard_montage(montage_name)
    # Match case-insensitively where possible by renaming to montage casing.
    dig_names = {n.lower(): n for n in montage.ch_names}
    rename = {}
    for ch in raw.ch_names:
        key = ch.lower()
        if key in dig_names and dig_names[key] != ch:
            rename[ch] = dig_names[key]
    if rename:
        raw.rename_channels(rename)
    raw.set_montage(montage, on_missing="ignore", match_case=False, verbose=False)
    types = raw.get_channel_types()
    has_loc = 0
    missing: list[str] = []
    for i, ch in enumerate(raw.ch_names):
        loc = raw.info["chs"][i]["loc"][:3]
        if not np.allclose(loc, 0):
            has_loc += 1
        elif types[i] == "eeg":
            missing.append(ch)
    return {
        "montage": montage_name,
        "matched": has_loc,
        "missing": missing,
        "renamed": rename,
    }


def load_text_matrix(
    source: str | Path,
    *,
    sfreq: float,
    transpose: bool = False,
    channel_names: list[str] | None = None,
    include_columns: Sequence[int] | None = None,
    column_selection: Sequence[dict[str, Any]] | None = None,
    montage: str | None = None,
) -> tuple[Any, dict[str, Any]]:
    """
    Load text matrix as MNE Raw.

    Default layout: rows = samples, columns = file columns.
    Non-EEG columns (ignore/time) are dropped; stim/misc/eeg are kept.
    """
    import mne

    if sfreq <= 0:
        raise ValueError("sfreq must be > 0 for text imports")

    path = Path(source).expanduser().resolve()
    sniffed = _sniff_structure(path, max_preview_rows=2)
    n_cols = int(sniffed["n_cols"])
    if n_cols <= 0:
        raise ValueError("cannot parse text matrix: no numeric columns detected")

    delimiter = sniffed["delimiter"]
    skip = int(sniffed["data_start"])

    selection = _normalize_column_selection(
        n_cols,
        column_selection,
        channel_names,
        include_columns,
        header=sniffed["header"],
    )
    keep = [c for c in selection if c["role"] not in {ROLE_IGNORE, ROLE_TIME}]
    if not keep:
        raise ValueError("no columns selected as eeg/stim/misc — mark at least one channel")

    usecols = [c["index"] for c in keep]
    kw = _loadtxt_kwargs(delimiter, skip, usecols)
    data = np.loadtxt(path, **kw)
    if data.ndim == 1:
        data = data.reshape(-1, 1)

    if transpose:
        # File rows = channels: after usecols, shape is (n_kept_rows_as_channels?, …)
        # Transpose mode with column selection is unusual; treat loaded matrix as channels×samples
        # if rows == len(keep), else samples×channels then transpose.
        if data.shape[0] == len(keep):
            data_ch_time = data.astype(np.float64, copy=False)
        else:
            data_ch_time = data.T.astype(np.float64, copy=False)
    else:
        data_ch_time = data.T.astype(np.float64, copy=False)

    n_ch, n_times = data_ch_time.shape
    if n_ch != len(keep):
        raise ValueError(
            f"loaded {n_ch} channels but selection has {len(keep)} kept columns "
            f"(check transpose / column selection)"
        )

    ch_names = [c["name"] for c in keep]
    ch_types = [_role_to_mne_type(c["role"]) for c in keep]
    info = mne.create_info(ch_names=ch_names, sfreq=float(sfreq), ch_types=ch_types)
    raw = mne.io.RawArray(data_ch_time, info, verbose=False)
    montage_info = _apply_montage(raw, montage)

    meta_out = {
        "format": "text_matrix",
        "path": str(path),
        "delimiter": "whitespace" if delimiter == r"\s+" else delimiter,
        "n_cols": n_cols,
        "file_size_bytes": int(sniffed["size"]),
        "sfreq": float(sfreq),
        "transpose": transpose,
        "n_channels": n_ch,
        "n_times": n_times,
        "duration_sec": n_times / float(sfreq),
        "column_selection": selection,
        "kept_columns": keep,
        "montage": montage_info,
    }
    return raw, meta_out


def _channels_from_raw(raw: Any, montage_name: str | None) -> list[Channel]:
    channels: list[Channel] = []
    types = raw.get_channel_types()
    for i, name in enumerate(raw.ch_names):
        mne_type = types[i]
        ctype = ChannelType.TRIGGER if mne_type == "stim" else (
            ChannelType.MISC if mne_type == "misc" else ChannelType.EEG
        )
        loc = raw.info["chs"][i]["loc"][:3]
        location = None
        if not np.allclose(loc, 0):
            location = ChannelLocation(
                x=float(loc[0]),
                y=float(loc[1]),
                z=float(loc[2]),
                coordinate_frame="head",
                source="standard" if montage_name else "imported",
            )
        channels.append(
            Channel(
                name=name,
                type=ctype,
                location=location,
                status=ChannelStatus.UNKNOWN,
                metadata={"montage": montage_name} if montage_name else {},
            )
        )
    return channels


def _cheap_source_digest(path: Path, size: int) -> str:
    """Avoid hashing an entire multi-GB text dump on import."""
    h = hashlib.sha256()
    h.update(str(size).encode())
    with path.open("rb") as fh:
        head = fh.read(1_048_576)
        h.update(head)
        if size > 2_097_152:
            fh.seek(max(0, size - 1_048_576))
            h.update(fh.read(1_048_576))
    return h.hexdigest()


def import_text_recording(
    source: str | Path,
    *,
    subject_id: str,
    session_id: str,
    run_id: str,
    sfreq: float,
    transpose: bool = False,
    channel_names: list[str] | None = None,
    include_columns: Sequence[int] | None = None,
    column_selection: Sequence[dict[str, Any]] | None = None,
    montage: str | None = None,
    artifact_dir: Path | None = None,
) -> tuple[Recording, DatasetArtifact, Any]:
    path = Path(source).expanduser().resolve()
    raw, meta = load_text_matrix(
        path,
        sfreq=sfreq,
        transpose=transpose,
        channel_names=channel_names,
        include_columns=include_columns,
        column_selection=column_selection,
        montage=montage,
    )

    fif_path: Path | None = None
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        fif_path = artifact_dir / f"import_{path.stem}_raw.fif"
        # fmt=0 / less aggressive compression is faster for large imports
        raw.save(fif_path, overwrite=True, verbose=False)

    digest = _cheap_source_digest(path, int(meta.get("file_size_bytes") or path.stat().st_size))
    montage_name = (meta.get("montage") or {}).get("montage")
    channels = _channels_from_raw(raw, montage_name)

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
            "montage": montage,
            "kept_columns": meta.get("kept_columns"),
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

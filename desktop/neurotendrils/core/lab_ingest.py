"""Normalize lab EEG sources (.set, .mat, numeric .txt) into FIF dataset members."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

from neurotendrils.core.dataset_manifest import (
    DEFAULT_FILENAME_CLASS_MAP,
    DatasetManifest,
    DatasetMember,
    LabelConfig,
    SplitConfig,
    class_from_filename,
    create_empty_manifest,
    new_dataset_dir,
    save_manifest,
)
from neurotendrils.core.eeg_formats import matched_suffix
from neurotendrils.core.naming import sanitize_base_name

ProgressCb = Callable[[dict[str, Any]], None]

# Formats we can pull into a multi-file dataset (beyond already-FIF studio files).
LAB_IMPORT_SUFFIXES: tuple[str, ...] = (
    "fif",
    "fif.gz",
    "edf",
    "bdf",
    "set",
    "gdf",
    "mat",
    "txt",
)


class IngestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _emit(cb: ProgressCb | None, **payload: Any) -> None:
    if cb is not None:
        cb(payload)


def _load_numeric_txt(path: Path) -> np.ndarray:
    """Load comma- or whitespace-separated numeric matrix (rows = time)."""
    try:
        arr = np.loadtxt(path, delimiter=",", dtype=np.float64)
    except ValueError:
        arr = np.loadtxt(path, dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr


def _constant_channel_warnings(data_ct: np.ndarray, *, names: list[str]) -> list[str]:
    """data_ct: (n_channels, n_times)."""
    warnings: list[str] = []
    for i, name in enumerate(names):
        row = data_ct[i]
        if row.size == 0:
            continue
        if float(np.nanstd(row)) < 1e-9:
            warnings.append(f"Constant channel {name} (value={float(row[0]):.4g})")
        elif float(np.nanmax(np.abs(row - 187500.0))) < 1e-3:
            warnings.append(f"Saturated channel {name} (187500)")
    return warnings


def _event_id_for_class(class_name: str, class_names: list[str]) -> dict[str, int]:
    if class_name not in class_names:
        class_names.append(class_name)
    code = class_names.index(class_name) + 1
    return {class_name: code}


def _window_epochs_from_raw(
    raw: Any,
    *,
    class_name: str,
    class_names: list[str],
    window_sec: float = 1.0,
) -> Any:
    """Cut fixed windows labeled with a single class (per-trial lab files)."""
    import mne

    sfreq = float(raw.info["sfreq"])
    n_times = raw.n_times
    win = max(8, int(round(window_sec * sfreq)))
    if n_times < win:
        win = n_times
    starts = list(range(0, max(1, n_times - win + 1), win))
    if not starts:
        starts = [0]
    event_id = _event_id_for_class(class_name, class_names)
    code = event_id[class_name]
    events = np.array([[s, 0, code] for s in starts], dtype=np.int64)
    tmax = (win - 1) / sfreq
    return mne.Epochs(
        raw,
        events,
        event_id=event_id,
        tmin=0.0,
        tmax=tmax,
        baseline=None,
        preload=True,
        reject_by_annotation=False,
        verbose="ERROR",
    )


def _is_matlab73(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(14).startswith(b"MATLAB 7.3")
    except OSError:
        return False


def _require_matlab73_stack(path: Path) -> None:
    """EEGLAB .set / v7.3 mats need pymatreader + h5py (scipy alone cannot open them)."""
    missing: list[str] = []
    try:
        import h5py  # noqa: F401
    except ImportError:
        missing.append("h5py")
    try:
        import pymatreader  # noqa: F401
    except ImportError:
        missing.append("pymatreader")
    if missing:
        pkgs = " ".join(missing)
        raise IngestError(
            "dependency_missing",
            f"{path.name} is MATLAB v7.3 (HDF5). Install missing packages in the app venv: "
            f"pip install {pkgs}. Or import the numeric .txt / For-ML .mat instead.",
        )


def normalize_mat(
    path: Path,
    dest: Path,
    *,
    class_names: list[str],
    warnings: list[str],
) -> tuple[Path, str | None]:
    """ML mat with data+label → epoched FIF. Returns (path, class_hint)."""
    import mne
    import scipy.io as sio

    if _is_matlab73(path):
        _require_matlab73_stack(path)

    try:
        payload = sio.loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except NotImplementedError as exc:
        # MATLAB v7.3 / HDF5 — scipy cannot load these; need pymatreader path elsewhere
        _require_matlab73_stack(path)
        raise IngestError(
            "unsupported_mat",
            f"{path.name} is MATLAB v7.3; could not read it ({exc}). "
            "Use For-ML data+label .mat, numeric .txt, or EEGLAB .set with pymatreader installed.",
        ) from exc

    keys = [k for k in payload if not k.startswith("__")]
    if "data" in payload and "label" in payload:
        data = np.asarray(payload["data"], dtype=np.float64)
        labels = np.asarray(payload["label"]).ravel().astype(np.int64)
        # Expect (n, t, c) or (n, c, t)
        if data.ndim != 3:
            raise IngestError("invalid_mat", f"{path.name}: data must be 3-D")
        if data.shape[0] != len(labels):
            # maybe (c, t, n)
            if data.shape[-1] == len(labels):
                data = np.transpose(data, (2, 1, 0))
            else:
                raise IngestError(
                    "invalid_mat",
                    f"{path.name}: data/label length mismatch {data.shape} vs {labels.shape}",
                )
        # data now (n, a, b) — detect channels vs time (channels usually ≤128, time ≥ channels)
        n, a, b = data.shape
        if a <= 128 and b > a:
            # (n, c, t)
            trials = data
        elif b <= 128 and a > b:
            # (n, t, c)
            trials = np.transpose(data, (0, 2, 1))
        else:
            trials = np.transpose(data, (0, 2, 1))  # MEMA For-ML: (n, 500, 32)

        n_ch = int(trials.shape[1])
        n_times = int(trials.shape[2])
        # Infer sfreq from common window length 500 @ 500 Hz
        sfreq = 500.0 if n_times in {250, 500, 1000} else 250.0
        ch_names = [f"EEG{i+1:02d}" for i in range(n_ch)]
        info = mne.create_info(ch_names, sfreq=sfreq, ch_types="eeg")
        unique = sorted(int(x) for x in np.unique(labels))
        local_names = [f"class_{c}" for c in unique]
        for name in local_names:
            if name not in class_names:
                class_names.append(name)
        event_id = {name: (unique[i] if unique[i] != 0 else 1000 + i) for i, name in enumerate(local_names)}
        # Ensure positive distinct codes
        codes = []
        for lab in labels:
            name = f"class_{int(lab)}"
            codes.append(event_id[name])
        events = np.array([[i * n_times, 0, c] for i, c in enumerate(codes)], dtype=np.int64)
        epochs = mne.EpochsArray(
            trials.astype(np.float64),
            info,
            events=events,
            event_id=event_id,
            tmin=0.0,
            verbose="ERROR",
        )
        for w in _constant_channel_warnings(trials.mean(axis=0), names=ch_names):
            if w not in warnings:
                warnings.append(w)
        dest.parent.mkdir(parents=True, exist_ok=True)
        epochs.save(str(dest), overwrite=True, verbose="ERROR")
        return dest, None

    # Continuous trial keys lst_eeg*
    trial_keys = sorted(
        [k for k in keys if str(k).startswith("lst_eeg")],
        key=lambda s: int("".join(ch for ch in str(s) if ch.isdigit()) or "0"),
    )
    if trial_keys:
        raise IngestError(
            "mat_needs_split",
            f"{path.name} has continuous trials ({', '.join(trial_keys[:3])}…). "
            "Import For-ML Subject*.mat (data+label) or per-trial .set/.txt files instead.",
        )

    raise IngestError(
        "unsupported_mat",
        f"{path.name}: expected variables data+label (got {keys[:8]})",
    )


def normalize_txt(
    path: Path,
    dest: Path,
    *,
    sfreq: float,
    class_names: list[str],
    filename_map: dict[str, str],
    warnings: list[str],
    n_eeg: int = 32,
) -> tuple[Path, str | None]:
    import mne

    arr = _load_numeric_txt(path)  # (n_times, n_cols)
    n_cols = int(arr.shape[1])
    eeg_cols = min(n_eeg, n_cols)
    eeg = arr[:, :eeg_cols].T  # (n_ch, n_times)
    ch_names = [f"EEG{i+1:02d}" for i in range(eeg_cols)]
    for w in _constant_channel_warnings(eeg, names=ch_names):
        if w not in warnings:
            warnings.append(w)

    info = mne.create_info(ch_names, sfreq=float(sfreq), ch_types="eeg")
    raw = mne.io.RawArray(eeg, info, verbose="ERROR")

    # Optional marker column (e.g. MEMA Data2 col 34)
    if n_cols >= eeg_cols + 2:
        marker = arr[:, -1]
        # Build annotations where marker value changes and is non-zero
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
            raw.set_annotations(mne.Annotations(onsets, [0.0] * len(onsets), descriptions))

    hint = class_from_filename(path.stem, filename_map)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if hint:
        epochs = _window_epochs_from_raw(
            raw, class_name=hint, class_names=class_names, window_sec=1.0
        )
        epochs.save(str(dest), overwrite=True, verbose="ERROR")
        return dest, hint

    raw_dest = dest.with_name(dest.name.replace("-epo.fif", "_raw.fif"))
    raw.save(str(raw_dest), overwrite=True, verbose="ERROR")
    return raw_dest, None


def normalize_set_or_mne(
    path: Path,
    dest: Path,
    *,
    class_names: list[str],
    filename_map: dict[str, str],
    warnings: list[str],
) -> tuple[Path, str | None]:
    import mne

    hint = class_from_filename(path.stem, filename_map)
    suffix = matched_suffix(str(path), ("set", "fif", "fif.gz", "edf", "bdf", "gdf"))

    # EEGLAB .set from many labs is MATLAB v7.3 (needs pymatreader + h5py).
    if suffix == "set" and _is_matlab73(path):
        _require_matlab73_stack(path)

    # Try epochs first
    try:
        epochs = mne.read_epochs(str(path), preload=True, verbose="ERROR")
        dest.parent.mkdir(parents=True, exist_ok=True)
        epochs.save(str(dest), overwrite=True, verbose="ERROR")
        return dest, hint
    except Exception:  # noqa: BLE001
        pass

    try:
        if suffix == "set":
            raw = mne.io.read_raw_eeglab(str(path), preload=True, verbose="ERROR")
        else:
            raw = mne.io.read_raw(str(path), preload=True, verbose="ERROR")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "h5py" in msg.lower() or "hdf" in msg.lower() or "7.3" in msg:
            _require_matlab73_stack(path)
        raise IngestError("read_failed", f"Could not read {path.name}: {exc}") from exc

    picks = mne.pick_types(raw.info, eeg=True, meg=False, exclude="bads")
    if len(picks):
        data = raw.get_data(picks=picks)
        names = [raw.ch_names[i] for i in picks]
        for w in _constant_channel_warnings(data, names=names):
            if w not in warnings:
                warnings.append(w)

    dest.parent.mkdir(parents=True, exist_ok=True)
    if hint and (
        raw.annotations is None
        or len(raw.annotations) == 0
        or len(set(raw.annotations.description)) < 2
    ):
        epochs = _window_epochs_from_raw(
            raw, class_name=hint, class_names=class_names, window_sec=1.0
        )
        epochs.save(str(dest), overwrite=True, verbose="ERROR")
        return dest, hint

    raw_dest = dest.with_name(dest.name.replace("-epo.fif", "_raw.fif"))
    raw.save(str(raw_dest), overwrite=True, verbose="ERROR")
    return raw_dest, hint


def normalize_source(
    source: Path,
    dest_stem: Path,
    *,
    sfreq: float,
    class_names: list[str],
    filename_map: dict[str, str],
    warnings: list[str],
) -> tuple[Path, str | None]:
    """Write a FIF next to dest_stem (stem path without deciding -epo vs raw)."""
    lower = source.name.lower()
    epo_dest = dest_stem.with_name(dest_stem.name + "-epo.fif")
    if lower.endswith(".mat"):
        return normalize_mat(source, epo_dest, class_names=class_names, warnings=warnings)
    if lower.endswith(".txt"):
        return normalize_txt(
            source,
            epo_dest,
            sfreq=sfreq,
            class_names=class_names,
            filename_map=filename_map,
            warnings=warnings,
        )
    if lower.endswith((".fif", ".fif.gz", ".edf", ".bdf", ".set", ".gdf")):
        # Copy companions for set
        return normalize_set_or_mne(
            source,
            epo_dest,
            class_names=class_names,
            filename_map=filename_map,
            warnings=warnings,
        )
    raise IngestError("unsupported", f"Unsupported lab format: {source.name}")


def create_dataset_from_sources(
    sources: list[str | Path],
    *,
    name: str,
    sfreq: float = 500.0,
    project_root: str | None = None,
    label_source: str = "filename",
    filename_map: dict[str, str] | None = None,
    on_progress: ProgressCb | None = None,
) -> tuple[str, DatasetManifest]:
    """Normalize sources into datasets/<name>/ and write dataset.json.

    Returns (manifest_path, manifest).
    """
    paths = [Path(s).expanduser().resolve() for s in sources]
    if not paths:
        raise IngestError("invalid_args", "No source files provided")
    for p in paths:
        if not p.is_file():
            raise IngestError("file_not_found", f"Not found: {p}")

    filename_map = dict(filename_map or DEFAULT_FILENAME_CLASS_MAP)
    out_dir = new_dataset_dir(name, project_root=project_root)
    members_dir = out_dir / "members"
    members_dir.mkdir(parents=True, exist_ok=True)

    manifest = create_empty_manifest(out_dir.name, sfreq=sfreq)
    manifest.label = LabelConfig(source=label_source, map=filename_map)  # type: ignore[arg-type]
    manifest.split = SplitConfig()
    class_names: list[str] = []
    warnings: list[str] = []

    total = len(paths)
    for index, source in enumerate(paths):
        _emit(
            on_progress,
            stage="ingest",
            message=f"Importing {source.name} ({index + 1}/{total})…",
            current=index + 1,
            total=total,
        )
        stem = sanitize_base_name(source.stem, f"member_{index + 1}")
        dest_stem = members_dir / stem
        # Copy .fdt beside .set into a temp working copy if needed
        work = source
        if source.suffix.lower() == ".set":
            fdt = source.with_suffix(".fdt")
            if fdt.is_file():
                # mne reads from original path; fine as long as fdt is adjacent
                work = source
        try:
            out_path, hint = normalize_source(
                work,
                dest_stem,
                sfreq=sfreq,
                class_names=class_names,
                filename_map=filename_map,
                warnings=warnings,
            )
        except IngestError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise IngestError("ingest_failed", f"{source.name}: {exc}") from exc

        rel = out_path.relative_to(out_dir).as_posix()
        manifest.members.append(
            DatasetMember(
                id=stem,
                path=rel,
                source_path=str(source),
                class_hint=hint,
                group=None,
                role=None,
            )
        )

    manifest.label.class_names = list(class_names)
    manifest.meta["sfreq"] = sfreq
    manifest.meta["warnings"] = warnings
    manifest.meta["source_count"] = total
    manifest_path = save_manifest(manifest, out_dir)
    _emit(
        on_progress,
        stage="done",
        message=f"Dataset ready · {len(manifest.members)} members",
        path=str(manifest_path),
    )
    return str(manifest_path.resolve()), manifest

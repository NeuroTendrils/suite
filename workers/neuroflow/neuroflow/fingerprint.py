"""Fingerprint a local EEG recording.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class FingerprintError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def fingerprint_file(path: str | Path) -> dict[str, Any]:
    """Return a JSON-serializable fingerprint for *path*.

    Supports continuous Raw and epoched FIF. Never includes raw sample arrays.
    """
    file_path = Path(path).expanduser()
    if not str(path).strip():
        raise FingerprintError("invalid_path", "path is required")
    if not file_path.is_file():
        raise FingerprintError("file_not_found", f"file not found: {file_path}")

    try:
        import mne
    except ImportError as exc:
        raise FingerprintError(
            "dependency_missing",
            "mne is required for fingerprint; install neuroflow requirements",
        ) from exc

    kind = "raw"
    data: Any
    try:
        data = mne.io.read_raw(str(file_path), preload=False, verbose="ERROR")
    except Exception as raw_exc:  # noqa: BLE001
        try:
            data = mne.read_epochs(str(file_path), preload=False, verbose="ERROR")
            kind = "epochs"
        except Exception as epo_exc:  # noqa: BLE001
            raise FingerprintError(
                "read_failed",
                f"failed to read recording: {raw_exc}",
            ) from epo_exc

    info = data.info
    sfreq = float(info["sfreq"])
    ch_names = [str(name) for name in info["ch_names"]]
    try:
        ch_types = [str(t) for t in data.get_channel_types()]
    except Exception:  # noqa: BLE001
        ch_types = ["eeg"] * len(ch_names)

    if kind == "raw":
        n_times = int(data.n_times)
        duration_sec = float(n_times / sfreq) if sfreq > 0 else 0.0
        n_epochs = None
    else:
        n_epochs = int(len(data))
        try:
            epoch_len = float(data.times[-1] - data.times[0]) if len(data.times) else 0.0
        except Exception:  # noqa: BLE001
            epoch_len = 0.0
        n_times = int(round(epoch_len * sfreq)) if epoch_len > 0 else 0
        duration_sec = float(n_epochs * epoch_len) if epoch_len > 0 else 0.0

    meas_date = info.get("meas_date")
    meas_date_out = None if meas_date is None else str(meas_date)

    annotations = _annotation_summary(data, kind)

    return {
        "path": str(file_path.resolve()),
        "file_name": file_path.name,
        "file_format": _format_from_suffix(file_path),
        "mne_kind": kind,
        "n_channels": len(ch_names),
        "ch_names": ch_names,
        "ch_types": ch_types,
        "sfreq": sfreq,
        "n_times": n_times,
        "n_epochs": n_epochs,
        "duration_sec": duration_sec,
        "highpass": _optional_float(info.get("highpass")),
        "lowpass": _optional_float(info.get("lowpass")),
        "meas_date": meas_date_out,
        "montage_hint": _montage_hint(ch_names),
        "n_annotations": annotations["n_annotations"],
        "annotation_labels": annotations["labels"],
        "has_events": annotations["has_events"],
        "task_hint": _task_hint(file_path, annotations["labels"]),
        "mne_version": str(getattr(mne, "__version__", "unknown")),
    }


def _annotation_summary(data: Any, kind: str) -> dict[str, Any]:
    labels: list[str] = []
    n_annotations = 0
    has_events = False
    if kind == "raw":
        ann = getattr(data, "annotations", None)
        if ann is not None and len(ann) > 0:
            n_annotations = int(len(ann))
            counts: dict[str, int] = {}
            for desc in ann.description:
                key = str(desc)
                if key.upper().startswith("BAD"):
                    continue
                counts[key] = counts.get(key, 0) + 1
            labels = sorted(counts.keys())
            has_events = bool(labels)
        if not has_events:
            try:
                import mne

                events = mne.find_events(data, shortest_event=1, verbose="ERROR")
                has_events = len(events) > 0
            except Exception:  # noqa: BLE001
                has_events = False
    else:
        event_id = getattr(data, "event_id", None) or {}
        labels = sorted(str(k) for k in event_id.keys())
        has_events = bool(labels)
        n_annotations = int(len(data)) if has_events else 0
    return {
        "n_annotations": n_annotations,
        "labels": labels,
        "has_events": has_events,
    }


def _task_hint(path: Path, labels: list[str]) -> str | None:
    """Best-effort MI vs ERP guess for recommend() epoch windows."""
    text = " ".join([path.stem.lower(), *[label.lower() for label in labels]])
    erp_tokens = ("p300", "erp", "oddball", "n400", "mmn", "target", "standard")
    mi_tokens = ("mi", "motor", "imagery", "left_hand", "right_hand", "feet", "tongue")
    if any(token in text for token in erp_tokens):
        return "erp"
    if any(token in text for token in mi_tokens):
        return "motor_imagery"
    return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _format_from_suffix(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".fif.gz"):
        return "fif.gz"
    suffix = path.suffix.lower().lstrip(".")
    return suffix or "unknown"


def _montage_hint(ch_names: list[str]) -> str | None:
    if not ch_names:
        return None
    normalized = {name.strip().lower() for name in ch_names}
    landmarks = {"fp1", "fp2", "fz", "cz", "pz", "o1", "o2", "t7", "t8", "c3", "c4"}
    hits = len(normalized & landmarks)
    if hits >= 4:
        return "standard_1020"
    if hits >= 2:
        return "standard_1020_partial"
    stripped = {name.removeprefix("eeg").strip() for name in normalized}
    if len(stripped & landmarks) >= 4:
        return "standard_1020"
    return None

"""EMOTIV Insight CSV adapter. EEG is in microvolts; MNE stores volts.

Metadata, counters, quality, motion and marker columns never become EEG channels.
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.domain.models import Channel, DatasetArtifact, Recording

CHANNELS = ("AF3", "T7", "Pz", "T8", "AF4")
SFREQ = 128.0


def _name(value: str) -> str:
    return value.strip().removeprefix("EEG.").casefold()


def _header(path: Path) -> tuple[list[str], int, str]:
    metadata = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for i, row in enumerate(csv.reader(handle)):
            if i > 30:
                break
            names = [_name(c) for c in row]
            if all(c.casefold() in names for c in CHANNELS):
                if len(names) != len(set(names)):
                    raise ValueError("duplicate columns in Insight export")
                return row, i, " ".join(metadata)
            metadata.append(",".join(row))
    raise ValueError("Insight CSV must contain AF3, T7, Pz, T8 and AF4")


class InsightImporter:
    name = "emotiv_insight"

    def can_handle(self, source: str | Path) -> bool:
        path = Path(source)
        if path.suffix.lower() != ".csv" or not path.is_file():
            return False
        try:
            header, _, metadata = _header(path)
            return (
                "emotiv" in metadata.lower()
                or "insight" in metadata.lower()
                or all(f"EEG.{c}" in header for c in CHANNELS)
            )
        except ValueError:
            return False

    def inspect(self, source: str | Path) -> dict[str, Any]:
        _header_names, _, metadata = _header(Path(source))
        rate = re.search(r"sampling\s*rate\s*[:=]\s*([\d.]+)", metadata, re.IGNORECASE)
        if rate and float(rate.group(1)) != SFREQ:
            return {
                "format": self.name,
                "status": "unreadable",
                "error": "Insight profile requires 128 Hz; export metadata differs",
            }
        return {
            "format": self.name,
            "status": "needs_config",
            "self_describing": False,
            "required_config": ["sfreq"],
            "sfreq": SFREQ,
            "n_channels": 5,
            "ch_names": list(CHANNELS),
            "units": "uV",
            "warnings": [
                "Insight profile: confirm 128 Hz and microvolt EEG export. Non-EEG columns are excluded."
            ],
        }

    def import_recording(
        self,
        source: str | Path,
        *,
        subject_id: str,
        session_id: str,
        run_id: str,
        sfreq: float | None = None,
        artifact_dir: Path | None = None,
        **_: Any,
    ):
        import mne

        from suite_backend.scientific.io.stim_events import extract_events_from_raw

        if sfreq != SFREQ:
            raise ValueError("Confirm the Insight sampling rate: sfreq=128 is required")
        path = Path(source).resolve()
        header, skip, _ = _header(path)
        names = [_name(c) for c in header]
        rows = []
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            for _i in range(skip + 1):
                next(reader)
            rows = [r for r in reader if r and any(v.strip() for v in r)]
        if len(rows) < 2 or any(len(r) != len(header) for r in rows):
            raise ValueError("Insight CSV is empty, truncated or has inconsistent columns")
        data = np.asarray([[float(r[names.index(c.casefold())]) for c in CHANNELS] for r in rows])
        if not np.isfinite(data).all():
            raise ValueError("Insight EEG contains non-finite samples")
        raw = mne.io.RawArray(
            data.T * 1e-6, mne.create_info(list(CHANNELS), SFREQ, "eeg"), verbose=False
        )
        raw.set_montage("standard_1020")
        onset, duration, description = [], [], []
        if "interpolated" in names:
            for i, row in enumerate(rows):
                if float(row[names.index("interpolated")]):
                    onset.append(i / SFREQ)
                    duration.append(1 / SFREQ)
                    description.append("BAD_interpolated")
        time_col = next((c for c in ("timestamp", "time", "time_stamp_s") if c in names), None)
        gaps = 0
        if time_col:
            times = np.asarray([float(r[names.index(time_col)]) for r in rows])
            dt = np.diff(times)
            if not np.isfinite(times).all() or np.any(dt <= 0):
                raise ValueError("Insight timestamps must be finite and strictly increasing")
            if abs(float(np.median(dt)) - 1 / SFREQ) > 0.002:
                raise ValueError("Insight timestamps do not match 128 Hz")
            for i in np.where(dt > 1.5 / SFREQ)[0]:
                gaps += 1
                onset.append((int(i) + 1) / SFREQ)
                duration.append(0.0)
                description.append("BAD boundary")
        marker_col = next((c for c in ("markervalueint", "marker", "markers") if c in names), None)
        if marker_col:
            previous = ""
            for i, row in enumerate(rows):
                value = row[names.index(marker_col)].strip()
                if value and value not in {"0", "0.0"} and value != previous:
                    onset.append(i / SFREQ)
                    duration.append(0.0)
                    description.append(f"marker/{value}")
                previous = value
        raw.set_annotations(mne.Annotations(onset, duration, description))
        channels = [Channel(name=c, unit="uV") for c in CHANNELS]
        recording = Recording(
            subject_id=subject_id,
            session_id=session_id,
            run_id=run_id,
            source_format=self.name,
            sampling_rate=SFREQ,
            duration=len(rows) / SFREQ,
            channel_count=5,
            channels=channels,
            events=extract_events_from_raw(raw),
            acquisition_metadata={
                "device": "EMOTIV Insight",
                "original_path": str(path),
                "units": "uV",
                "timestamp_gaps": gaps,
                "excluded_columns": [
                    h for h in header if _name(h) not in {c.casefold() for c in CHANNELS}
                ],
            },
        )
        paths = {"source": str(path)}
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            fif = artifact_dir / f"insight_{recording.id}_raw.fif"
            raw.save(fif, overwrite=False, verbose=False)
            paths["fif"] = str(fif)
        recording.source_files = [paths.get("fif", str(path))]
        artifact = DatasetArtifact(
            type="raw_recording",
            operation="import",
            recording_id=recording.id,
            parameters={"format": self.name, "sfreq": SFREQ, "units": "uV"},
            paths=paths,
            checksum=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        recording.artifact_id = artifact.id
        return recording, artifact, raw

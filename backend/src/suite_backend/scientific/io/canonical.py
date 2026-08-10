"""Canonical loaders and post-import normalization for Recording + DataStream."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.domain.migrate import recording_from_stream_rollup
from suite_backend.domain.models import DataStream, Modality, Recording


class StreamSamples:
    """Normalized in-memory view of a DataStream."""

    def __init__(
        self,
        *,
        stream: DataStream,
        data: np.ndarray,
        times: np.ndarray,
        sfreq: float,
        channel_names: list[str],
        units: str | None,
    ) -> None:
        self.stream = stream
        self.data = data  # (n_channels, n_times)
        self.times = times
        self.sfreq = float(sfreq)
        self.channel_names = channel_names
        self.units = units

    @property
    def n_channels(self) -> int:
        return int(self.data.shape[0])

    @property
    def n_times(self) -> int:
        return int(self.data.shape[1])


def _resolve_path(path: str | Path | None) -> Path | None:
    if not path:
        return None
    p = Path(path).expanduser()
    return p if p.exists() else None


def ensure_eeg_sample_paths(stream: DataStream, recording: Recording | None = None) -> DataStream:
    """Ensure EEG streams point at a FIF under sample_paths when available."""
    paths = dict(stream.sample_paths or {})
    if paths.get("fif") and _resolve_path(paths["fif"]):
        return stream
    candidates: list[str] = []
    candidates.extend(stream.source_files or [])
    if recording:
        candidates.extend(recording.source_files or [])
    for c in candidates:
        if str(c).endswith((".fif", ".fif.gz")) and _resolve_path(c):
            paths["fif"] = str(Path(c).resolve())
            stream.sample_paths = paths
            break
    return stream


def load_stream_samples(stream: DataStream) -> StreamSamples:
    """
    Load any modality stream into a common (channels × time) array + times.

    Preference order:
      1. sample_paths['data_npy'] (+ optional times_npy)
      2. sample_paths['fif'] / source FIF via MNE
      3. other MNE-readable source_files for EEG-like streams
    """
    stream = ensure_eeg_sample_paths(stream)
    paths = stream.sample_paths or {}

    data_npy = _resolve_path(paths.get("data_npy"))
    if data_npy is not None:
        data = np.load(data_npy)
        if data.ndim == 1:
            data = data.reshape(1, -1)
        times_npy = _resolve_path(paths.get("times_npy") or stream.timestamp_path)
        if times_npy is not None:
            times = np.load(times_npy).astype(np.float64)
        else:
            sfreq = float(stream.sampling_rate or 1.0)
            times = np.arange(data.shape[1], dtype=np.float64) / sfreq
        names = [c.name for c in stream.channels] or [f"ch{i+1}" for i in range(data.shape[0])]
        sfreq = float(stream.sampling_rate or (1.0 / np.median(np.diff(times)) if len(times) > 1 else 1.0))
        return StreamSamples(
            stream=stream,
            data=np.asarray(data, dtype=np.float64),
            times=times,
            sfreq=sfreq,
            channel_names=names[: data.shape[0]],
            units=stream.units,
        )

    fif = _resolve_path(paths.get("fif"))
    if fif is None:
        for src in stream.source_files:
            if str(src).endswith((".fif", ".fif.gz")):
                fif = _resolve_path(src)
                if fif:
                    break

    if fif is not None:
        import mne

        raw = mne.io.read_raw_fif(fif, preload=True, verbose=False)
        data = raw.get_data()
        times = raw.times.copy()
        return StreamSamples(
            stream=stream,
            data=np.asarray(data, dtype=np.float64),
            times=np.asarray(times, dtype=np.float64),
            sfreq=float(raw.info["sfreq"]),
            channel_names=list(raw.ch_names),
            units=stream.units or "uV",
        )

    # Last resort: MNE readers for original EEG vendor files
    if stream.modality == Modality.EEG and stream.source_files:
        import mne
        from suite_backend.scientific.io.importers import _read_mne_raw

        src = Path(stream.source_files[0])
        if src.exists():
            raw = _read_mne_raw(src)
            raw.load_data()
            return StreamSamples(
                stream=stream,
                data=np.asarray(raw.get_data(), dtype=np.float64),
                times=np.asarray(raw.times, dtype=np.float64),
                sfreq=float(raw.info["sfreq"]),
                channel_names=list(raw.ch_names),
                units=stream.units or "uV",
            )

    raise ValueError(
        f"cannot load stream {stream.id} ({stream.modality.value}): "
        f"no sample_paths or readable source (paths={stream.sample_paths})"
    )


def load_primary_eeg_raw(recording: Recording, streams: list[DataStream] | None = None):
    """Return an MNE Raw for the recording's primary EEG stream (canonical FIF preferred)."""
    import mne

    streams = streams or []
    eeg = next((s for s in streams if s.modality == Modality.EEG), None)
    if eeg is None and streams:
        # no EEG — cannot build Raw
        raise ValueError(f"recording {recording.id} has no EEG DataStream")
    if eeg is not None:
        eeg = ensure_eeg_sample_paths(eeg, recording)
        fif = _resolve_path((eeg.sample_paths or {}).get("fif"))
        if fif is None:
            for src in list(eeg.source_files) + list(recording.source_files):
                if str(src).endswith((".fif", ".fif.gz")):
                    fif = _resolve_path(src)
                    if fif:
                        break
        if fif is not None:
            return mne.io.read_raw_fif(fif, preload=True, verbose=False)
        # Build RawArray from loaded samples
        samples = load_stream_samples(eeg)
        info = mne.create_info(samples.channel_names, samples.sfreq, ch_types="eeg")
        return mne.io.RawArray(samples.data, info, verbose=False)

    # Legacy recording without streams list passed in
    if not recording.source_files:
        raise ValueError("recording has no source files or EEG streams")
    source = Path(recording.source_files[0])
    suffix = source.suffix.lower()
    if suffix in {".fif", ".fif.gz"}:
        return mne.io.read_raw_fif(source, preload=True, verbose=False)
    from suite_backend.scientific.io.importers import _read_mne_raw

    raw = _read_mne_raw(source)
    raw.load_data()
    return raw


def normalize_recording(
    recording: Recording,
    streams: list[DataStream],
) -> tuple[Recording, list[DataStream], dict[str, Any]]:
    """
    Normalize a recording + its streams into the common internal representation.

    - Ensure EEG streams have FIF sample_paths when possible
    - Ensure external streams have data_npy sample_paths
    - Roll up Recording convenience fields from primary EEG (else first stream)
    - Stamp provenance.normalized
    """
    report: dict[str, Any] = {
        "recording_id": recording.id,
        "streams": [],
        "warnings": [],
        "ok": True,
    }
    updated: list[DataStream] = []
    for stream in streams:
        entry: dict[str, Any] = {
            "stream_id": stream.id,
            "modality": stream.modality.value,
            "actions": [],
        }
        if stream.modality == Modality.EEG:
            before = dict(stream.sample_paths or {})
            stream = ensure_eeg_sample_paths(stream, recording)
            if stream.sample_paths != before:
                entry["actions"].append("set_fif_sample_path")
        else:
            if not (stream.sample_paths or {}).get("data_npy"):
                report["warnings"].append(
                    f"stream {stream.id} ({stream.modality.value}) missing data_npy sample path"
                )
                report["ok"] = False
            else:
                entry["actions"].append("has_data_npy")

        # Verify loadable
        try:
            samples = load_stream_samples(stream)
            stream.n_samples = samples.n_times
            stream.sampling_rate = samples.sfreq
            stream.duration = float(samples.times[-1] - samples.times[0]) if len(samples.times) else stream.duration
            if not stream.channels and samples.channel_names:
                # leave channels as-is if present
                pass
            entry["n_channels"] = samples.n_channels
            entry["n_times"] = samples.n_times
            entry["sfreq"] = samples.sfreq
            entry["actions"].append("verified_load")
        except Exception as exc:  # noqa: BLE001
            entry["error"] = str(exc)
            report["warnings"].append(str(exc))
            report["ok"] = False

        prov = dict(stream.provenance or {})
        prov["normalized"] = True
        stream.provenance = prov
        updated.append(stream)
        report["streams"].append(entry)

    recording = recording_from_stream_rollup(recording, updated)
    recording.stream_ids = [s.id for s in updated]
    recording.preprocessing_state = {
        **dict(recording.preprocessing_state or {}),
        "normalized": True,
    }
    return recording, updated, report

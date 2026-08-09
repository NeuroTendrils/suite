from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from suite_backend.domain.models import (
    Channel,
    ChannelLocation,
    ChannelStatus,
    ChannelType,
    DatasetArtifact,
    Event,
    Recording,
)


class Importer(Protocol):
    name: str

    def can_handle(self, source: str | Path) -> bool: ...
    def inspect(self, source: str | Path) -> dict[str, Any]: ...
    def import_recording(
        self,
        source: str | Path,
        *,
        subject_id: str,
        session_id: str,
        run_id: str,
    ) -> tuple[Recording, DatasetArtifact, Any]: ...


def _channel_type(ch_type: str) -> ChannelType:
    mapping = {
        "eeg": ChannelType.EEG,
        "eog": ChannelType.EOG,
        "ecg": ChannelType.ECG,
        "emg": ChannelType.EMG,
        "stim": ChannelType.TRIGGER,
        "misc": ChannelType.MISC,
    }
    return mapping.get(ch_type.lower(), ChannelType.MISC)


class MneImporter:
    """Importer backed by MNE for supported formats."""

    def __init__(self, name: str, extensions: tuple[str, ...]) -> None:
        self.name = name
        self.extensions = extensions

    def can_handle(self, source: str | Path) -> bool:
        path = Path(source)
        return path.suffix.lower() in self.extensions and path.exists()

    def inspect(self, source: str | Path) -> dict[str, Any]:
        raw = self._read(source)
        return {
            "format": self.name,
            "path": str(Path(source).resolve()),
            "n_channels": len(raw.ch_names),
            "sfreq": float(raw.info["sfreq"]),
            "n_times": int(raw.n_times),
            "duration_sec": float(raw.n_times / raw.info["sfreq"]),
            "ch_names": list(raw.ch_names),
        }

    def import_recording(
        self,
        source: str | Path,
        *,
        subject_id: str,
        session_id: str,
        run_id: str,
        **_: Any,
    ) -> tuple[Recording, DatasetArtifact, Any]:
        import hashlib

        path = Path(source).resolve()
        raw = self._read(path)
        import mne

        channels: list[Channel] = []
        for ch_name in raw.ch_names:
            loc = None
            try:
                idx = raw.ch_names.index(ch_name)
                loc_arr = raw.info["chs"][idx].get("loc")
                if loc_arr is not None and len(loc_arr) >= 3:
                    loc = ChannelLocation(
                        x=float(loc_arr[0]),
                        y=float(loc_arr[1]),
                        z=float(loc_arr[2]),
                        source="imported",
                    )
            except Exception:  # noqa: BLE001
                loc = None
            try:
                ctype = mne.channel_type(raw.info, raw.ch_names.index(ch_name))
            except Exception:  # noqa: BLE001
                ctype = "eeg"
            channels.append(
                Channel(
                    name=ch_name,
                    type=_channel_type(str(ctype)),
                    location=loc,
                    status=ChannelStatus.UNKNOWN,
                )
            )

        events: list[Event] = []
        try:
            import mne

            found = mne.events_from_annotations(raw, verbose=False)
            mne_events, event_id = found
            id_to_name = {v: k for k, v in event_id.items()}
            sfreq = float(raw.info["sfreq"])
            for row in mne_events:
                sample = int(row[0])
                code = int(row[2])
                name = id_to_name.get(code, str(code))
                events.append(
                    Event(
                        timestamp=sample / sfreq,
                        sample_index=sample,
                        code=str(code),
                        name=name,
                    )
                )
        except Exception:  # noqa: BLE001
            pass

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        recording = Recording(
            subject_id=subject_id,
            session_id=session_id,
            run_id=run_id,
            source_files=[str(path)],
            source_format=self.name,
            sampling_rate=float(raw.info["sfreq"]),
            duration=float(raw.n_times / raw.info["sfreq"]),
            channel_count=len(channels),
            channels=channels,
            events=events,
            acquisition_metadata={"mne_info_keys": list(raw.info.keys())},
        )
        artifact = DatasetArtifact(
            type="raw_recording",
            operation="import",
            parameters={"format": self.name, "source": str(path)},
            checksum=digest,
            paths={"source": str(path)},
            recording_id=recording.id,
        )
        recording.artifact_id = artifact.id
        return recording, artifact, raw

    def _read(self, source: str | Path):
        import mne

        path = Path(source)
        suffix = path.suffix.lower()
        if suffix == ".fif":
            return mne.io.read_raw_fif(path, preload=False, verbose=False)
        if suffix == ".edf":
            return mne.io.read_raw_edf(path, preload=False, verbose=False)
        if suffix == ".vhdr":
            return mne.io.read_raw_brainvision(path, preload=False, verbose=False)
        if suffix == ".set":
            return mne.io.read_raw_eeglab(path, preload=False, verbose=False)
        raise ValueError(f"unsupported extension for {self.name}: {suffix}")


class MatInspectImporter:
    name = "mat_ambiguous"

    def can_handle(self, source: str | Path) -> bool:
        path = Path(source)
        return path.suffix.lower() == ".mat" and path.exists()

    def inspect(self, source: str | Path) -> dict[str, Any]:
        return {
            "format": self.name,
            "path": str(Path(source).resolve()),
            "status": "needs_content_inspection",
            "warning": "MAT files are ambiguous; content inspection required before import",
        }

    def import_recording(self, *args, **kwargs):
        raise NotImplementedError("MAT import requires content-specific mapping (not yet implemented)")


class TextMatrixImporter:
    """Numeric matrix .txt/.csv/.tsv — requires sfreq on import."""

    name = "text_matrix"

    def can_handle(self, source: str | Path) -> bool:
        path = Path(source)
        return path.suffix.lower() in {".txt", ".csv", ".tsv"} and path.exists()

    def inspect(self, source: str | Path) -> dict[str, Any]:
        from suite_backend.scientific.io.text_matrix import inspect_text_matrix

        return inspect_text_matrix(source)

    def import_recording(
        self,
        source: str | Path,
        *,
        subject_id: str,
        session_id: str,
        run_id: str,
        sfreq: float | None = None,
        transpose: bool = False,
        channel_names: list[str] | None = None,
        artifact_dir: Path | None = None,
        **_: Any,
    ) -> tuple[Recording, DatasetArtifact, Any]:
        from suite_backend.scientific.io.text_matrix import import_text_recording

        if sfreq is None:
            raise ValueError(
                "text imports require sfreq (Hz). Pass sfreq when importing .txt/.csv/.tsv."
            )
        return import_text_recording(
            source,
            subject_id=subject_id,
            session_id=session_id,
            run_id=run_id,
            sfreq=float(sfreq),
            transpose=bool(transpose),
            channel_names=channel_names,
            artifact_dir=artifact_dir,
        )


class ImporterRegistry:
    def __init__(self, importers: list[Importer] | None = None) -> None:
        self.importers = list(importers or [])

    def register(self, importer: Importer) -> None:
        self.importers.append(importer)

    def find(self, source: str | Path) -> Importer | None:
        for importer in self.importers:
            if importer.can_handle(source):
                return importer
        return None

    def inspect(self, source: str | Path) -> dict[str, Any]:
        importer = self.find(source)
        if importer is None:
            return {"error": "no importer can handle source", "path": str(source)}
        return importer.inspect(source)


def get_default_registry() -> ImporterRegistry:
    return ImporterRegistry(
        [
            MneImporter("fif", (".fif",)),
            MneImporter("edf", (".edf",)),
            MneImporter("brainvision", (".vhdr",)),
            MneImporter("eeglab", (".set",)),
            MatInspectImporter(),
            TextMatrixImporter(),
        ]
    )

from __future__ import annotations

import hashlib
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


def _read_mne_raw(path: Path):
    import mne

    suffix = path.suffix.lower()
    readers = {
        ".fif": lambda p: mne.io.read_raw_fif(p, preload=False, verbose=False),
        ".edf": lambda p: mne.io.read_raw_edf(p, preload=False, verbose=False),
        ".bdf": lambda p: mne.io.read_raw_bdf(p, preload=False, verbose=False),
        ".gdf": lambda p: mne.io.read_raw_gdf(p, preload=False, verbose=False),
        ".vhdr": lambda p: mne.io.read_raw_brainvision(p, preload=False, verbose=False),
        ".set": lambda p: mne.io.read_raw_eeglab(p, preload=False, verbose=False),
        ".cnt": lambda p: mne.io.read_raw_cnt(p, preload=False, verbose=False),
    }
    reader = readers.get(suffix)
    if reader is None:
        raise ValueError(f"unsupported EEG extension: {suffix}")
    return reader(path)


class MneImporter:
    """Self-describing EEG formats via MNE — auto-import, no config required."""

    def __init__(self, name: str, extensions: tuple[str, ...]) -> None:
        self.name = name
        self.extensions = extensions

    def can_handle(self, source: str | Path) -> bool:
        path = Path(source)
        return path.suffix.lower() in self.extensions and path.exists()

    def inspect(self, source: str | Path) -> dict[str, Any]:
        path = Path(source).expanduser().resolve()
        try:
            raw = _read_mne_raw(path)
        except Exception as exc:  # noqa: BLE001
            return {
                "format": self.name,
                "path": str(path),
                "status": "unreadable",
                "self_describing": True,
                "required_config": [],
                "error": str(exc),
                "warnings": [str(exc)],
            }
        return {
            "format": self.name,
            "path": str(path),
            "status": "ready",
            "self_describing": True,
            "required_config": [],
            "optional_config": ["montage"],
            "n_channels": len(raw.ch_names),
            "sfreq": float(raw.info["sfreq"]),
            "n_times": int(raw.n_times),
            "duration_sec": float(raw.n_times / raw.info["sfreq"]),
            "ch_names": list(raw.ch_names),
            "warnings": [],
        }

    def import_recording(
        self,
        source: str | Path,
        *,
        subject_id: str,
        session_id: str,
        run_id: str,
        artifact_dir: Path | None = None,
        montage: str | None = None,
        **_: Any,
    ) -> tuple[Recording, DatasetArtifact, Any]:
        import mne

        path = Path(source).expanduser().resolve()
        raw = _read_mne_raw(path)
        if montage:
            from suite_backend.scientific.io.text_matrix import _apply_montage

            # Need preload for some set_montage paths; load if required
            if not getattr(raw, "preload", False):
                raw.load_data()
            _apply_montage(raw, montage)

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
                        source="eeg_trigger",
                    )
                )
        except Exception:  # noqa: BLE001
            pass

        fif_path: Path | None = None
        if artifact_dir is not None:
            artifact_dir.mkdir(parents=True, exist_ok=True)
            if not getattr(raw, "preload", False):
                raw.load_data()
            fif_path = artifact_dir / f"import_{path.stem}_raw.fif"
            raw.save(fif_path, overwrite=True, verbose=False)

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stored = [str(fif_path)] if fif_path else [str(path)]
        recording = Recording(
            subject_id=subject_id,
            session_id=session_id,
            run_id=run_id,
            source_files=stored,
            source_format=self.name,
            sampling_rate=float(raw.info["sfreq"]),
            duration=float(raw.n_times / raw.info["sfreq"]),
            channel_count=len(channels),
            channels=channels,
            events=events,
            acquisition_metadata={
                "original_path": str(path),
                "mne_info_keys": list(raw.info.keys()),
            },
        )
        artifact = DatasetArtifact(
            type="raw_recording",
            operation="import",
            parameters={"format": self.name, "source": str(path), "montage": montage},
            checksum=digest,
            paths={
                "source": str(path),
                **({"fif": str(fif_path)} if fif_path else {}),
            },
            recording_id=recording.id,
        )
        recording.artifact_id = artifact.id
        return recording, artifact, raw


class MatImporter:
    name = "mat"

    def can_handle(self, source: str | Path) -> bool:
        path = Path(source)
        return path.suffix.lower() == ".mat" and path.exists()

    def inspect(self, source: str | Path) -> dict[str, Any]:
        from suite_backend.scientific.io.mat_import import inspect_mat

        return inspect_mat(source)

    def import_recording(
        self,
        source: str | Path,
        *,
        subject_id: str,
        session_id: str,
        run_id: str,
        data_key: str | None = None,
        sfreq: float | None = None,
        transpose: bool = False,
        channel_names: list[str] | None = None,
        montage: str | None = None,
        artifact_dir: Path | None = None,
        **_: Any,
    ) -> tuple[Recording, DatasetArtifact, Any]:
        from suite_backend.scientific.io.mat_import import import_mat_recording

        if not data_key:
            raise ValueError(
                "MAT import requires config data_key (array name). Inspect the file first."
            )
        if sfreq is None:
            raise ValueError("MAT import requires config sfreq (Hz). Not inferred from file.")
        return import_mat_recording(
            source,
            subject_id=subject_id,
            session_id=session_id,
            run_id=run_id,
            data_key=data_key,
            sfreq=float(sfreq),
            transpose=bool(transpose),
            channel_names=channel_names,
            montage=montage,
            artifact_dir=artifact_dir,
        )


class TextMatrixImporter:
    """Numeric matrix .txt/.csv/.tsv — requires explicit sfreq (+ column roles)."""

    name = "text_matrix"

    def can_handle(self, source: str | Path) -> bool:
        path = Path(source)
        return path.suffix.lower() in {".txt", ".csv", ".tsv", ".asc"} and path.exists()

    def inspect(self, source: str | Path) -> dict[str, Any]:
        from suite_backend.scientific.io.text_matrix import inspect_text_matrix

        info = inspect_text_matrix(source)
        info["self_describing"] = False
        info["status"] = "needs_config" if info.get("status") == "ok" else info.get("status")
        info["required_config"] = ["sfreq"]
        info["optional_config"] = [
            "column_selection",
            "transpose",
            "channel_names",
            "montage",
        ]
        info.setdefault("warnings", [])
        info["warnings"] = list(info["warnings"]) + [
            "Text matrices are ambiguous: sfreq must be provided; review column roles before import"
        ]
        return info

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
        include_columns: list[int] | None = None,
        column_selection: list[dict[str, Any]] | None = None,
        montage: str | None = None,
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
            include_columns=include_columns,
            column_selection=column_selection,
            montage=montage,
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
            return {
                "error": "no importer can handle source",
                "path": str(source),
                "status": "error",
                "self_describing": False,
                "required_config": [],
            }
        return importer.inspect(source)


def get_default_registry() -> ImporterRegistry:
    return ImporterRegistry(
        [
            MneImporter("fif", (".fif",)),
            MneImporter("edf", (".edf",)),
            MneImporter("bdf", (".bdf",)),
            MneImporter("gdf", (".gdf",)),
            MneImporter("brainvision", (".vhdr",)),
            MneImporter("eeglab", (".set",)),
            MneImporter("neuroscan_cnt", (".cnt",)),
            MatImporter(),
            TextMatrixImporter(),
        ]
    )

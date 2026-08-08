"""Dataset / recording ingest schema (montage, events, aux, about).

Manual prep fields live here; NeuroFlow recipes consume the saved state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ChannelType = Literal["eeg", "eog", "emg", "ecg", "misc", "stim", "gyro", "other"]
EventSource = Literal["annotations", "stim", "sidecar", "filename", "manual"]


@dataclass
class AboutInfo:
    """Optional human-facing dataset description."""

    summary: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "tags": list(self.tags),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AboutInfo:
        raw = data or {}
        return cls(
            summary=str(raw.get("summary") or ""),
            tags=[str(t) for t in (raw.get("tags") or [])],
            notes=str(raw.get("notes") or ""),
        )


@dataclass
class MontageConfig:
    """Named standard montage or path to a custom DigMontage sidecar."""

    name: str | None = None  # e.g. standard_1020
    custom_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "custom_path": self.custom_path}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MontageConfig:
        raw = data or {}
        return cls(
            name=(str(raw["name"]) if raw.get("name") else None),
            custom_path=(str(raw["custom_path"]) if raw.get("custom_path") else None),
        )


@dataclass
class ChannelConfig:
    types: dict[str, ChannelType] = field(default_factory=dict)
    drop: list[str] = field(default_factory=list)
    bad: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "types": dict(self.types),
            "drop": list(self.drop),
            "bad": list(self.bad),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChannelConfig:
        raw = data or {}
        types_raw = raw.get("types") or {}
        return cls(
            types={str(k): str(v) for k, v in types_raw.items()},  # type: ignore[misc]
            drop=[str(x) for x in (raw.get("drop") or [])],
            bad=[str(x) for x in (raw.get("bad") or [])],
        )


@dataclass
class EventsConfig:
    source: EventSource = "annotations"
    code_map: dict[str, str] = field(default_factory=dict)  # code/desc → class
    ignore: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "code_map": dict(self.code_map),
            "ignore": list(self.ignore),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EventsConfig:
        raw = data or {}
        source = raw.get("source") or "annotations"
        return cls(
            source=source,  # type: ignore[arg-type]
            code_map={str(k): str(v) for k, v in (raw.get("code_map") or {}).items()},
            ignore=[str(x) for x in (raw.get("ignore") or [])],
        )


@dataclass
class AuxStream:
    """Paired non-EEG stream (EMG, gyro, …) with optional sync offset."""

    kind: str
    path: str
    offset_sec: float = 0.0
    channels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuxStream:
        return cls(
            kind=str(data.get("kind") or "misc"),
            path=str(data.get("path") or ""),
            offset_sec=float(data.get("offset_sec") or 0.0),
            channels=[str(c) for c in (data.get("channels") or [])],
        )


@dataclass
class IngestSchema:
    about: AboutInfo = field(default_factory=AboutInfo)
    montage: MontageConfig = field(default_factory=MontageConfig)
    channels: ChannelConfig = field(default_factory=ChannelConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    aux: list[AuxStream] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "about": self.about.to_dict(),
            "montage": self.montage.to_dict(),
            "channels": self.channels.to_dict(),
            "events": self.events.to_dict(),
            "aux": [a.to_dict() for a in self.aux],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> IngestSchema:
        raw = data or {}
        return cls(
            about=AboutInfo.from_dict(raw.get("about")),
            montage=MontageConfig.from_dict(raw.get("montage")),
            channels=ChannelConfig.from_dict(raw.get("channels")),
            events=EventsConfig.from_dict(raw.get("events")),
            aux=[AuxStream.from_dict(a) for a in (raw.get("aux") or []) if isinstance(a, dict)],
        )


def validate_ingest_schema(schema: IngestSchema | dict[str, Any]) -> str | None:
    """Return an error message, or None if valid."""
    if isinstance(schema, dict):
        try:
            schema = IngestSchema.from_dict(schema)
        except Exception as exc:  # noqa: BLE001
            return f"Invalid ingest schema: {exc}"

    if schema.montage.name and schema.montage.custom_path:
        return "montage: set either name or custom_path, not both."

    for stream in schema.aux:
        if not stream.path.strip():
            return "aux: each stream needs a path."
        if not stream.kind.strip():
            return "aux: each stream needs a kind (emg, gyro, …)."

    for name, ch_type in schema.channels.types.items():
        if not name.strip():
            return "channels.types: empty channel name."
        if ch_type not in {"eeg", "eog", "emg", "ecg", "misc", "stim", "gyro", "other"}:
            return f"channels.types: unsupported type “{ch_type}” for {name}."

    if schema.events.source not in {
        "annotations",
        "stim",
        "sidecar",
        "filename",
        "manual",
    }:
        return f"events.source: unsupported “{schema.events.source}”."

    return None

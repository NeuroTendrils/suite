"""Multi-file training datasets: JSON manifest under project datasets/."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from neurotendrils.core.naming import sanitize_base_name, unique_dir
from neurotendrils.core.projectdir import ProjectDir, resolve_path

MANIFEST_NAME = "dataset.json"
LabelSource = Literal["embedded", "filename", "sidecar"]
SplitMode = Literal["stratified", "by_member_role", "by_group"]
MemberRole = Literal["train", "test", "unused"]

DEFAULT_FILENAME_CLASS_MAP: dict[str, str] = {
    "_n": "neutral",
    "_r": "relaxing",
    "_a": "concentrating",
    "neutral": "neutral",
    "relaxing": "relaxing",
    "concentrating": "concentrating",
}


@dataclass
class DatasetMember:
    id: str
    path: str
    group: str | None = None
    role: MemberRole | None = None
    source_path: str | None = None
    class_hint: str | None = None


@dataclass
class LabelConfig:
    source: LabelSource = "embedded"
    map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FILENAME_CLASS_MAP))
    class_names: list[str] = field(default_factory=list)


@dataclass
class SplitConfig:
    mode: SplitMode = "stratified"
    val_fraction: float = 0.2
    seed: int = 42


@dataclass
class DatasetManifest:
    version: int
    name: str
    created_at: str
    members: list[DatasetMember]
    label: LabelConfig
    split: SplitConfig
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def root_dir(self) -> Path | None:
        """Directory containing dataset.json when loaded from disk."""
        return self.meta.get("_root_dir")  # type: ignore[return-value]

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "version": self.version,
            "name": self.name,
            "created_at": self.created_at,
            "members": [asdict(m) for m in self.members],
            "label": {
                "source": self.label.source,
                "map": dict(self.label.map),
                "class_names": list(self.label.class_names),
            },
            "split": {
                "mode": self.split.mode,
                "val_fraction": float(self.split.val_fraction),
                "seed": int(self.split.seed),
            },
            "meta": {k: v for k, v in self.meta.items() if not str(k).startswith("_")},
        }
        return payload


def is_dataset_manifest(path: str | Path) -> bool:
    p = Path(path)
    if p.is_dir():
        return (p / MANIFEST_NAME).is_file()
    return p.is_file() and p.name == MANIFEST_NAME


def manifest_path_for(path: str | Path) -> Path:
    p = Path(path)
    if p.is_dir():
        return p / MANIFEST_NAME
    return p


def load_manifest(path: str | Path) -> DatasetManifest:
    manifest_file = manifest_path_for(path)
    if not manifest_file.is_file():
        raise FileNotFoundError(f"Dataset manifest not found: {manifest_file}")
    try:
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid dataset manifest: {exc}") from exc
    return _from_dict(data, root_dir=manifest_file.parent)


def save_manifest(manifest: DatasetManifest, directory: str | Path) -> Path:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    out = root / MANIFEST_NAME
    out.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    manifest.meta["_root_dir"] = root
    return out


def _from_dict(data: dict[str, Any], *, root_dir: Path) -> DatasetManifest:
    members = [
        DatasetMember(
            id=str(m.get("id") or f"m{i}"),
            path=str(m.get("path") or ""),
            group=m.get("group"),
            role=m.get("role"),
            source_path=m.get("source_path"),
            class_hint=m.get("class_hint"),
        )
        for i, m in enumerate(data.get("members") or [])
    ]
    label_raw = data.get("label") or {}
    split_raw = data.get("split") or {}
    manifest = DatasetManifest(
        version=int(data.get("version") or 1),
        name=str(data.get("name") or root_dir.name),
        created_at=str(data.get("created_at") or ""),
        members=members,
        label=LabelConfig(
            source=label_raw.get("source") or "embedded",  # type: ignore[arg-type]
            map=dict(label_raw.get("map") or DEFAULT_FILENAME_CLASS_MAP),
            class_names=list(label_raw.get("class_names") or []),
        ),
        split=SplitConfig(
            mode=split_raw.get("mode") or "stratified",  # type: ignore[arg-type]
            val_fraction=float(split_raw.get("val_fraction") or 0.2),
            seed=int(split_raw.get("seed") or 42),
        ),
        meta=dict(data.get("meta") or {}),
    )
    manifest.meta["_root_dir"] = root_dir
    return manifest


def resolve_member_path(manifest: DatasetManifest, member: DatasetMember) -> Path:
    root = manifest.meta.get("_root_dir")
    p = Path(member.path)
    if p.is_file():
        return p.resolve()
    if root is not None:
        candidate = (Path(root) / member.path).resolve()
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Dataset member missing: {member.path}")


def class_from_filename(
    stem: str, mapping: dict[str, str] | None = None
) -> str | None:
    mapping = mapping or DEFAULT_FILENAME_CLASS_MAP
    lower = stem.lower()
    for token, name in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if token.lower() in lower:
            return name
    return None


def new_dataset_dir(name: str, *, project_root: str | None = None) -> Path:
    root = project_root if project_root is not None else ProjectDir.instance().root
    if not root:
        raise RuntimeError("Project folder is not set")
    datasets = Path(root) / "datasets"
    stem = sanitize_base_name(name, "dataset")
    return unique_dir(datasets, stem)


def create_empty_manifest(name: str, *, sfreq: float | None = None) -> DatasetManifest:
    return DatasetManifest(
        version=1,
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        members=[],
        label=LabelConfig(source="filename", map=dict(DEFAULT_FILENAME_CLASS_MAP)),
        split=SplitConfig(),
        meta={"sfreq": sfreq} if sfreq is not None else {},
    )


def wrap_single_file_as_manifest(
    file_path: str | Path, *, name: str | None = None
) -> DatasetManifest:
    """In-memory 1-member dataset pointing at an existing project file."""
    p = resolve_path(file_path)
    return DatasetManifest(
        version=1,
        name=name or p.stem,
        created_at=datetime.now(timezone.utc).isoformat(),
        members=[
            DatasetMember(id=sanitize_base_name(p.stem, "member"), path=str(p))
        ],
        label=LabelConfig(source="embedded"),
        split=SplitConfig(),
        meta={},
    )


def list_dataset_manifests(project_root: str | None = None) -> list[Path]:
    root = project_root if project_root is not None else ProjectDir.instance().root
    if not root:
        return []
    datasets = Path(root) / "datasets"
    if not datasets.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(datasets.iterdir()):
        if path.is_dir() and (path / MANIFEST_NAME).is_file():
            found.append(path / MANIFEST_NAME)
    return found


def inspect_manifest_light(manifest: DatasetManifest) -> dict[str, Any]:
    """Filesystem-level summary (no MNE). Heavy label stats come from the worker."""
    members_ok = 0
    missing = 0
    hints: dict[str, int] = {}
    for member in manifest.members:
        try:
            resolve_member_path(manifest, member)
            members_ok += 1
        except OSError:
            missing += 1
        hint = member.class_hint or class_from_filename(
            Path(member.path).stem, manifest.label.map
        )
        if hint:
            hints[hint] = hints.get(hint, 0) + 1
    return {
        "name": manifest.name,
        "n_members": len(manifest.members),
        "n_members_ok": members_ok,
        "n_missing": missing,
        "label_source": manifest.label.source,
        "split_mode": manifest.split.mode,
        "filename_class_files": hints,
        "sfreq": manifest.meta.get("sfreq"),
        "warnings": list(manifest.meta.get("warnings") or []),
    }

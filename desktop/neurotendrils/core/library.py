"""Local library scan for Hub."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from neurotendrils.core.eeg_formats import IMPORT_SUFFIXES, matches_suffix
from neurotendrils.core.projectdir import ProjectDir, resolve_path

Kind = Literal["plan", "dataset", "model"]


@dataclass
class LibraryEntry:
    kind: Kind
    id: str
    title: str
    subtitle: str
    path: str
    size_bytes: int
    modified: float
    extra: dict[str, Any]


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def scan_plans() -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    plans_dir = ProjectDir.instance().plans_dir()
    if not plans_dir.is_dir():
        return entries
    for path in sorted(plans_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        steps = data.get("steps") or []
        title = str(data.get("name") or path.stem)
        entries.append(
            LibraryEntry(
                kind="plan",
                id=path.stem,
                title=title,
                subtitle=f"{len(steps)} steps",
                path=str(path),
                size_bytes=_file_size(path),
                modified=_mtime(path),
                extra={
                    "dataset_path": data.get("dataset_path", ""),
                    "steps": len(steps),
                },
            )
        )
    return entries


def scan_datasets() -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    datasets_dir = ProjectDir.instance().datasets_dir()
    if not datasets_dir.is_dir():
        return entries
    for path in sorted(datasets_dir.iterdir()):
        if not path.is_file() or not matches_suffix(str(path), IMPORT_SUFFIXES):
            continue
        entries.append(
            LibraryEntry(
                kind="dataset",
                id=path.name,
                title=path.name,
                subtitle=path.suffix.lstrip(".").upper() or "FILE",
                path=str(path),
                size_bytes=_file_size(path),
                modified=_mtime(path),
                extra={},
            )
        )
    return entries


def scan_models() -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    models_dir = ProjectDir.instance().models_dir()
    if not models_dir.is_dir():
        return entries
    for model_dir in sorted(models_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        meta_path = model_dir / "model.json"
        if not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("kind") != "neurostudio_model":
            continue
        artifact_rel = str(data.get("artifact") or "")
        artifact_path = resolve_path(model_dir / artifact_rel) if artifact_rel else model_dir
        # Prevent path traversal via model.json artifact field.
        try:
            artifact_path.relative_to(resolve_path(model_dir))
        except ValueError:
            artifact_path = model_dir

        exported = str(data.get("exported_at") or "")
        try:
            modified = datetime.fromisoformat(exported.replace("Z", "+00:00")).timestamp()
        except ValueError:
            modified = _mtime(meta_path)

        title = str(data.get("title") or model_dir.name)
        fmt = str(data.get("format") or "")
        template = str(data.get("template_id") or "")
        entries.append(
            LibraryEntry(
                kind="model",
                id=model_dir.name,
                title=title,
                subtitle=f"{template} · {fmt}".strip(" ·"),
                path=str(model_dir),
                size_bytes=_file_size(artifact_path) if artifact_path.is_file() else _file_size(meta_path),
                modified=modified,
                extra={
                    "artifact": str(artifact_path),
                    "template_id": template,
                    "format": fmt,
                    "publish": data.get("publish", {}),
                    "metrics": data.get("metrics", {}),
                },
            )
        )
    entries.sort(key=lambda e: e.modified, reverse=True)
    return entries


def scan_all() -> dict[str, list[LibraryEntry]]:
    return {
        "plans": scan_plans(),
        "datasets": scan_datasets(),
        "models": scan_models(),
    }

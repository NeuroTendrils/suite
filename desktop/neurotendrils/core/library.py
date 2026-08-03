"""Local library scan for Hub."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from neurotendrils.core.eeg_formats import IMPORT_SUFFIXES, extension_badge, matches_suffix
from neurotendrils.core.projectdir import ProjectDir, resolve_path

Kind = Literal["plan", "dataset", "model", "run"]


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


def _stat_size_mtime(path: Path) -> tuple[int, float]:
    try:
        st = path.stat()
        return st.st_size, st.st_mtime
    except OSError:
        return 0, 0.0


def scan_plans() -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    plans_dir = ProjectDir.instance().plans_dir()
    if not plans_dir.is_dir():
        return entries
    for path in sorted(plans_dir.glob("*.json")):
        if path.is_symlink():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        steps = data.get("steps") or []
        title = str(data.get("name") or path.stem)
        size_bytes, modified = _stat_size_mtime(path)
        entries.append(
            LibraryEntry(
                kind="plan",
                id=path.stem,
                title=title,
                subtitle=f"{len(steps)} steps",
                path=str(path),
                size_bytes=size_bytes,
                modified=modified,
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
        if path.is_symlink() or not path.is_file():
            continue
        if not matches_suffix(str(path), IMPORT_SUFFIXES):
            continue
        size_bytes, modified = _stat_size_mtime(path)
        entries.append(
            LibraryEntry(
                kind="dataset",
                id=path.name,
                title=path.name,
                subtitle=extension_badge(str(path)),
                path=str(path),
                size_bytes=size_bytes,
                modified=modified,
                extra={},
            )
        )
    return entries


def scan_models() -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    models_dir = ProjectDir.instance().models_dir()
    if not models_dir.is_dir():
        return entries
    project = ProjectDir.instance()
    for model_dir in sorted(models_dir.iterdir()):
        if model_dir.is_symlink() or not model_dir.is_dir():
            continue
        meta_path = model_dir / "model.json"
        if meta_path.is_symlink() or not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("kind") != "neurostudio_model":
            continue
        artifact_rel = str(data.get("artifact") or "")
        artifact_path = resolve_path(model_dir / artifact_rel) if artifact_rel else model_dir
        # Clamp traversal and require the artifact stay inside the project root.
        try:
            artifact_path.relative_to(resolve_path(model_dir))
        except ValueError:
            artifact_path = model_dir
        if not project.contains(artifact_path):
            artifact_path = model_dir

        exported = str(data.get("exported_at") or "")
        try:
            modified = datetime.fromisoformat(exported.replace("Z", "+00:00")).timestamp()
        except ValueError:
            _, modified = _stat_size_mtime(meta_path)

        title = str(data.get("title") or model_dir.name)
        fmt = str(data.get("format") or "")
        template = str(data.get("template_id") or "")
        size_path = artifact_path if artifact_path.is_file() else meta_path
        size_bytes, _ = _stat_size_mtime(size_path)
        entries.append(
            LibraryEntry(
                kind="model",
                id=model_dir.name,
                title=title,
                subtitle=f"{template} · {fmt}".strip(" ·"),
                path=str(model_dir),
                size_bytes=size_bytes,
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


def scan_runs() -> list[LibraryEntry]:
    entries: list[LibraryEntry] = []
    runs_dir = ProjectDir.instance().runs_dir()
    if not runs_dir.is_dir():
        return entries
    for path in runs_dir.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        size_bytes, modified = _stat_size_mtime(path)
        entries.append(
            LibraryEntry(
                kind="run",
                id=path.name,
                title=path.name,
                subtitle=path.suffix.lstrip(".").upper() or "OUTPUT",
                path=str(path),
                size_bytes=size_bytes,
                modified=modified,
                extra={},
            )
        )
    entries.sort(key=lambda e: e.modified, reverse=True)
    return entries


def scan_all() -> dict[str, list[LibraryEntry]]:
    return {
        "plans": scan_plans(),
        "datasets": scan_datasets(),
        "models": scan_models(),
        "runs": scan_runs(),
    }

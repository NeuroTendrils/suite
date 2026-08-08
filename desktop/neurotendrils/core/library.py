"""Local library scan for Hub."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from PySide6.QtCore import QObject, Signal

from neurotendrils.core.eeg_formats import IMPORT_SUFFIXES, extension_badge, matches_suffix
from neurotendrils.core.projectdir import ProjectDir, resolve_path

Kind = Literal["plan", "dataset", "model", "run", "template"]


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


class LibraryBus(QObject):
    """Broadcast when project contents change so pages can rescan."""

    changed = Signal()

    _instance: LibraryBus | None = None

    @classmethod
    def instance(cls) -> LibraryBus:
        if cls._instance is None:
            cls._instance = LibraryBus()
        return cls._instance


def notify_library_changed() -> None:
    LibraryBus.instance().changed.emit()


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

    # Multi-file dataset manifests (directories with dataset.json).
    for path in sorted(datasets_dir.iterdir()):
        if path.is_symlink() or not path.is_dir():
            continue
        manifest = path / "dataset.json"
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        members = data.get("members") or []
        label = data.get("label") or {}
        classes = label.get("class_names") or []
        title = str(data.get("name") or path.name)
        size_bytes, modified = _stat_size_mtime(manifest)
        # Roll up member sizes when cheap.
        for member in members[:64]:
            rel = str(member.get("path") or "")
            try:
                sz, mt = _stat_size_mtime(path / rel)
                size_bytes += sz
                modified = max(modified, mt)
            except OSError:
                pass
        class_bit = f"{len(classes)} classes" if classes else str(label.get("source") or "labels")
        about = data.get("about") or {}
        montage = data.get("montage") or {}
        subjects = {
            str(m.get("subject") or m.get("group") or "")
            for m in members
            if (m.get("subject") or m.get("group"))
        }
        subjects.discard("")
        entries.append(
            LibraryEntry(
                kind="dataset",
                id=path.name,
                title=title,
                subtitle=f"Dataset · {len(members)} files · {class_bit}",
                path=str(manifest),
                size_bytes=size_bytes,
                modified=modified,
                extra={
                    "manifest": True,
                    "n_members": len(members),
                    "label_source": label.get("source"),
                    "class_names": classes,
                    "about_summary": about.get("summary") or "",
                    "montage": montage.get("name") or montage.get("custom_path") or "",
                    "n_subjects": len(subjects),
                },
            )
        )

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


def _run_entry_from_dir(run_dir: Path) -> LibraryEntry | None:
    """One NeuroFlow execution: a folder with run.json (+ cleaned.fif)."""
    meta_path = run_dir / "run.json"
    if meta_path.is_symlink() or not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}

    output_path = Path(str(data.get("output_path") or run_dir / "cleaned.fif"))
    if not output_path.is_file():
        for candidate in sorted(run_dir.glob("*.fif")):
            if not candidate.is_symlink():
                output_path = candidate
                break
        else:
            output_path = meta_path

    size_bytes, modified = _stat_size_mtime(output_path)
    if not modified:
        _, modified = _stat_size_mtime(meta_path)

    result = data.get("result") or {}
    n_steps = result.get("n_steps")
    if n_steps is None:
        plan = data.get("plan") or {}
        n_steps = len(plan.get("steps") or [])
    kind = str(result.get("output_kind") or extension_badge(str(output_path)))
    input_name = Path(str(data.get("input_path") or "")).name
    subtitle_parts = [f"{n_steps} steps" if n_steps else "run"]
    if kind:
        subtitle_parts.append(str(kind))
    if input_name:
        subtitle_parts.append(input_name)

    return LibraryEntry(
        kind="run",
        id=run_dir.name,
        title=run_dir.name,
        subtitle=" · ".join(subtitle_parts),
        path=str(run_dir),
        size_bytes=size_bytes,
        modified=modified,
        extra={
            "output_path": str(output_path),
            "meta_path": str(meta_path),
            "input_path": str(data.get("input_path") or ""),
            "n_steps": n_steps,
            "output_kind": kind,
        },
    )


def scan_templates() -> list[LibraryEntry]:
    """Saved NeuroStudio template configs under ``templates/*.json``."""
    from neurotendrils.core.studio_io import CONFIG_KIND, find_template

    entries: list[LibraryEntry] = []
    templates_dir = ProjectDir.instance().templates_dir()
    if not templates_dir.is_dir():
        return entries
    for path in templates_dir.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("kind") not in {CONFIG_KIND, None}:
            continue
        template_id = str(data.get("template_id") or "")
        config = data.get("config")
        if not template_id or not isinstance(config, dict):
            continue
        tmpl = find_template(template_id)
        title = str(data.get("name") or (tmpl or {}).get("title") or path.stem)
        size_bytes, modified = _stat_size_mtime(path)
        saved = str(data.get("saved_at") or "")
        if saved:
            try:
                modified = datetime.fromisoformat(saved.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        family = str((tmpl or {}).get("model_family") or "")
        subtitle = f"{template_id}" + (f" · {family}" if family else "")
        entries.append(
            LibraryEntry(
                kind="template",
                id=path.stem,
                title=title,
                subtitle=subtitle,
                path=str(path),
                size_bytes=size_bytes,
                modified=modified,
                extra={
                    "template_id": template_id,
                    "config": config,
                    "dataset_path": data.get("dataset_path", ""),
                },
            )
        )
    entries.sort(key=lambda e: e.modified, reverse=True)
    return entries


def scan_runs() -> list[LibraryEntry]:
    """Scan NeuroFlow run folders under ``runs/<name>_<stamp>/``.

    A run is one plan execution: metadata in ``run.json`` and the cleaned
    recording beside it. Flat ``*.json`` files left from older seeds are
    ignored so they do not masquerade as real runs.
    """
    entries: list[LibraryEntry] = []
    runs_dir = ProjectDir.instance().runs_dir()
    if not runs_dir.is_dir():
        return entries
    for path in runs_dir.iterdir():
        if path.is_symlink() or not path.is_dir():
            continue
        entry = _run_entry_from_dir(path)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda e: e.modified, reverse=True)
    return entries


def scan_all() -> dict[str, list[LibraryEntry]]:
    return {
        "plans": scan_plans(),
        "datasets": scan_datasets(),
        "models": scan_models(),
        "runs": scan_runs(),
        "templates": scan_templates(),
    }

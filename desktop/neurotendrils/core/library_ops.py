"""Rename / delete library records inside the active project."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from neurotendrils.core.library import LibraryEntry
from neurotendrils.core.naming import sanitize_base_name, unique_dir, unique_path
from neurotendrils.core.projectdir import PROJECT_META, ProjectDir


def delete_entry(entry: LibraryEntry) -> None:
    project = ProjectDir.instance()
    path = project.require_contains(entry.path, "record")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.is_file():
        path.unlink()
    else:
        raise FileNotFoundError(f"Nothing to delete at {path}")


def rename_entry(entry: LibraryEntry, new_name: str) -> str:
    """Rename a file or folder; returns the new path."""
    project = ProjectDir.instance()
    path = project.require_contains(entry.path, "record")
    if not path.exists():
        raise FileNotFoundError(f"Missing: {path}")

    stem = sanitize_base_name(new_name, path.stem if path.is_file() else path.name)
    parent = path.parent

    if path.is_file():
        suffix = path.suffix
        same = parent / f"{stem}{suffix}"
        if same.resolve() == path.resolve():
            return str(path)
        dest = unique_path(parent, stem, suffix)
        path.rename(dest)
        return str(dest)

    if stem == path.name:
        dest = path
    else:
        dest = unique_dir(parent, stem)
        path.rename(dest)
    meta = dest / PROJECT_META
    # Keep project.json name in sync when renaming a project folder from elsewhere.
    if meta.is_file():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["name"] = new_name.strip() or dest.name
                meta.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    return str(dest)


def rename_project(path: str, new_name: str) -> str:
    """Rename a project folder under the workspace; returns the new path."""
    project = ProjectDir.instance()
    workspace = Path(project.workspace)
    resolved = Path(path).expanduser().resolve(strict=False)
    try:
        resolved.relative_to(workspace.resolve(strict=False))
    except ValueError as exc:
        raise PermissionError("project must be inside the workspace") from exc
    if not resolved.is_dir():
        raise FileNotFoundError(f"Missing project: {resolved}")

    stem = sanitize_base_name(new_name, resolved.name)
    dest = resolved if stem == resolved.name else unique_dir(workspace, stem)
    if dest != resolved:
        resolved.rename(dest)

    meta = dest / PROJECT_META
    display = new_name.strip() or dest.name
    payload: dict = {
        "v": 1,
        "kind": "neurotendrils_project",
        "name": display,
    }
    if meta.is_file():
        try:
            existing = json.loads(meta.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                existing["name"] = display
                payload = existing
        except (OSError, json.JSONDecodeError):
            pass
    meta.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if project.root and Path(project.root).resolve(strict=False) == resolved:
        project.set_root(str(dest), persist=True)
    return str(dest)


def delete_project(path: str) -> None:
    project = ProjectDir.instance()
    workspace = Path(project.workspace)
    resolved = Path(path).expanduser().resolve(strict=False)
    try:
        resolved.relative_to(workspace.resolve(strict=False))
    except ValueError as exc:
        raise PermissionError("project must be inside the workspace") from exc
    if resolved == workspace.resolve(strict=False):
        raise PermissionError("cannot delete the workspace itself")
    if not resolved.is_dir():
        raise FileNotFoundError(f"Missing project: {resolved}")

    was_active = bool(project.root) and Path(project.root).resolve(strict=False) == resolved
    shutil.rmtree(resolved)
    if was_active:
        remaining = project.list_projects()
        if remaining:
            project.set_root(remaining[0].path, persist=True)
        else:
            created = project.create_project("Default")
            if created:
                project.set_root(created, persist=True)

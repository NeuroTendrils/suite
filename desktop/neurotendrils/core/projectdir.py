"""Workspace + active project sandbox.

All projects live under a workspace (default ``~/NeuroTendrils``). Each project
is its own folder with plans, datasets, models, runs, and templates.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QMessageBox, QWidget

from neurotendrils.core.naming import sanitize_base_name, unique_dir

ORG = "NeuroTendrils"
APP = "NeuroTendrils"
WORKSPACE_KEY = "workspace/root"
PROJECT_KEY = "project/active"
# Legacy single-folder key — migrated into workspace + active project on first load.
LEGACY_ROOT_KEY = "project/root"
SUBDIRS = ("plans", "datasets", "models", "runs", "templates")
PROJECT_META = "project.json"


def default_workspace() -> Path:
    return Path.home() / "NeuroTendrils"


def resolve_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    try:
        return p.resolve(strict=False)
    except OSError:
        return Path(os.path.normpath(str(p.absolute())))


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    path: str
    modified: float
    counts: dict[str, int]


def _looks_like_project(path: Path) -> bool:
    if not path.is_dir() or path.is_symlink():
        return False
    if (path / PROJECT_META).is_file():
        return True
    return any((path / name).is_dir() for name in SUBDIRS)


def _count_entries(project: Path) -> dict[str, int]:
    counts = {name: 0 for name in SUBDIRS}
    for name in SUBDIRS:
        folder = project / name
        if not folder.is_dir():
            continue
        try:
            counts[name] = sum(1 for item in folder.iterdir() if not item.name.startswith("."))
        except OSError:
            counts[name] = 0
    return counts


class ProjectDir(QObject):
    """Workspace root plus the currently open project."""

    root_changed = Signal(str)
    workspace_changed = Signal(str)

    _instance: ProjectDir | None = None

    def __init__(self) -> None:
        super().__init__()
        self._workspace = ""
        self._root = ""

    @classmethod
    def instance(cls) -> ProjectDir:
        if cls._instance is None:
            cls._instance = ProjectDir()
        return cls._instance

    def initialize(self, dialog_parent: QWidget | None = None) -> None:
        settings = QSettings(ORG, APP)
        workspace = str(settings.value(WORKSPACE_KEY, "") or "")
        active = str(settings.value(PROJECT_KEY, "") or "")

        # Migrate older builds that stored a single project path in PROJECT_KEY
        # before workspace existed as a separate concept.
        if not workspace:
            legacy = str(settings.value(LEGACY_ROOT_KEY, "") or "")
            if legacy and _looks_like_project(Path(legacy)):
                legacy_path = Path(legacy)
                # If legacy path already sits inside ~/NeuroTendrils, use parent
                # as workspace; otherwise keep legacy as the first project and
                # place the workspace beside it (or use default).
                default = default_workspace()
                try:
                    legacy_path.resolve().relative_to(default.resolve())
                    workspace = str(default)
                    active = legacy
                except ValueError:
                    if legacy_path.name and legacy_path.parent != legacy_path:
                        # e.g. /old/path/MyProject → workspace=/old/path
                        if _looks_like_project(legacy_path):
                            workspace = str(legacy_path.parent)
                            active = legacy
                        else:
                            workspace = legacy
                    else:
                        workspace = str(default)
            else:
                workspace = str(default_workspace())

        self.set_workspace(workspace, persist=True, dialog_parent=dialog_parent)
        self._migrate_flat_workspace()

        projects = self.list_projects()
        default_path = str(Path(self._workspace) / "Default")
        if active and Path(active).is_dir() and self.contains_workspace(active):
            self.set_root(active, persist=True, dialog_parent=dialog_parent)
        elif Path(default_path).is_dir() and _looks_like_project(Path(default_path)):
            self.set_root(default_path, persist=True, dialog_parent=dialog_parent)
        elif projects:
            self.set_root(projects[0].path, persist=True, dialog_parent=dialog_parent)
        else:
            # First launch: land in ~/NeuroTendrils/Default.
            created = self.create_project("Default", dialog_parent=dialog_parent)
            if created:
                self.set_root(created, persist=True, dialog_parent=dialog_parent)

    # ---------- workspace ----------

    @property
    def workspace(self) -> str:
        return self._workspace

    def set_workspace(
        self,
        workspace: str,
        *,
        persist: bool = True,
        dialog_parent: QWidget | None = None,
    ) -> None:
        path = resolve_path(workspace)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            if dialog_parent is not None:
                from neurotendrils.widgets.modals import alert, find_host

                message = (
                    f"The workspace {path} could not be created. "
                    "Please choose a different location in Settings."
                )
                if find_host(dialog_parent) is not None:
                    alert(dialog_parent, "Workspace Unavailable", message)
                else:
                    QMessageBox.warning(dialog_parent, "Workspace Unavailable", message)
        self._workspace = str(path)
        if persist:
            QSettings(ORG, APP).setValue(WORKSPACE_KEY, self._workspace)
        self.workspace_changed.emit(self._workspace)

    def _migrate_flat_workspace(self) -> None:
        """If the workspace itself holds datasets/plans/…, nest them into a project."""
        workspace = Path(self._workspace) if self._workspace else None
        if workspace is None or not workspace.is_dir():
            return
        try:
            children = [c for c in workspace.iterdir() if not c.name.startswith(".")]
        except OSError:
            return
        child_projects = [
            c for c in children if c.is_dir() and c.name not in SUBDIRS and _looks_like_project(c)
        ]
        if child_projects:
            return
        flat_dirs = [workspace / name for name in SUBDIRS if (workspace / name).is_dir()]
        if not flat_dirs:
            return
        target = workspace / "Default"
        try:
            target.mkdir(parents=True, exist_ok=True)
            for folder in flat_dirs:
                dest = target / folder.name
                if dest.exists():
                    continue
                folder.rename(dest)
            meta = target / PROJECT_META
            if not meta.is_file():
                meta.write_text(
                    json.dumps(
                        {
                            "v": 1,
                            "kind": "neurotendrils_project",
                            "name": "Default",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
        except OSError:
            return

    def contains_workspace(self, path: str | Path) -> bool:
        if not self._workspace or not path:
            return False
        resolved = resolve_path(path)
        root = resolve_path(self._workspace)
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            return resolved == root

    def list_projects(self) -> list[ProjectInfo]:
        workspace = Path(self._workspace) if self._workspace else None
        if workspace is None or not workspace.is_dir():
            return []
        projects: list[ProjectInfo] = []
        try:
            children = sorted(workspace.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return []
        for child in children:
            if child.name.startswith(".") or not _looks_like_project(child):
                continue
            # Skip the workspace itself if someone pointed workspace at a project.
            if resolve_path(child) == resolve_path(workspace) and (workspace / PROJECT_META).is_file():
                pass
            modified = child.stat().st_mtime
            meta_path = child / PROJECT_META
            name = child.name
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    name = str(meta.get("name") or name)
                    modified = max(modified, meta_path.stat().st_mtime)
                except (OSError, json.JSONDecodeError):
                    pass
            projects.append(
                ProjectInfo(
                    name=name,
                    path=str(child),
                    modified=modified,
                    counts=_count_entries(child),
                )
            )
        projects.sort(key=lambda p: p.modified, reverse=True)
        return projects

    def create_project(
        self, name: str, *, dialog_parent: QWidget | None = None
    ) -> str | None:
        if not self._workspace:
            self.set_workspace(str(default_workspace()), dialog_parent=dialog_parent)
        workspace = Path(self._workspace)
        stem = sanitize_base_name(name, "project")
        try:
            project_dir = unique_dir(workspace, stem)
            project_dir.mkdir(parents=True, exist_ok=False)
            for sub in SUBDIRS:
                (project_dir / sub).mkdir(parents=True, exist_ok=True)
            meta = {
                "v": 1,
                "kind": "neurotendrils_project",
                "name": name.strip() or project_dir.name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            (project_dir / PROJECT_META).write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )
        except OSError:
            if dialog_parent is not None:
                from neurotendrils.widgets.modals import alert

                alert(
                    dialog_parent,
                    "Could not create project",
                    f"Failed to create a project folder in {workspace}.",
                )
            return None
        return str(project_dir)

    # ---------- active project ----------

    def set_root(
        self,
        root: str,
        *,
        persist: bool = True,
        dialog_parent: QWidget | None = None,
    ) -> None:
        self._root = root
        root_path = Path(root)
        try:
            root_path.mkdir(parents=True, exist_ok=True)
            for name in SUBDIRS:
                (root_path / name).mkdir(parents=True, exist_ok=True)
            meta_path = root_path / PROJECT_META
            if not meta_path.is_file():
                meta_path.write_text(
                    json.dumps(
                        {
                            "v": 1,
                            "kind": "neurotendrils_project",
                            "name": root_path.name,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
        except OSError:
            if dialog_parent is not None:
                from neurotendrils.widgets.modals import alert, find_host

                message = (
                    f"The project folder {root} could not be created. "
                    "Please choose a different location in Settings."
                )
                if find_host(dialog_parent) is not None:
                    alert(dialog_parent, "Project Folder Unavailable", message)
                else:
                    QMessageBox.warning(
                        dialog_parent, "Project Folder Unavailable", message
                    )
        if persist:
            QSettings(ORG, APP).setValue(PROJECT_KEY, root)
            # Keep legacy key in sync for older tooling.
            QSettings(ORG, APP).setValue(LEGACY_ROOT_KEY, root)
        self.root_changed.emit(self._root)

    @property
    def root(self) -> str:
        return self._root

    def plans_dir(self) -> Path:
        return Path(self._root) / "plans"

    def datasets_dir(self) -> Path:
        return Path(self._root) / "datasets"

    def models_dir(self) -> Path:
        return Path(self._root) / "models"

    def runs_dir(self) -> Path:
        return Path(self._root) / "runs"

    def templates_dir(self) -> Path:
        return Path(self._root) / "templates"

    def contains(self, path: str | Path) -> bool:
        if not self._root or not path:
            return False
        resolved = resolve_path(path)
        resolved_root = resolve_path(self._root)
        try:
            resolved.relative_to(resolved_root)
            return True
        except ValueError:
            return resolved == resolved_root

    def require_contains(self, path: str | Path, label: str = "path") -> Path:
        """Resolve *path* and require it stays inside the active project."""
        raw = Path(path).expanduser()
        resolved = resolve_path(raw)
        if not self.contains(resolved):
            raise PermissionError(f"{label} must be inside the project folder")
        if raw.exists() or raw.parent.exists():
            try:
                real = Path(os.path.realpath(str(raw if raw.exists() else raw.parent)))
            except OSError:
                real = resolved
            check = real if raw.exists() else real / raw.name
            if not self.contains(check):
                raise PermissionError(f"{label} resolves outside the project folder")
        return resolved

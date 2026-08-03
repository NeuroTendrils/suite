"""Project sandbox: root path, subdirs, containment checks."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

ORG = "NeuroTendrils"
APP = "NeuroTendrils"
ROOT_KEY = "project/root"
SUBDIRS = ("plans", "datasets", "models", "runs", "learn")


def default_root() -> Path:
    return Path.home() / "NeuroTendrils"


def resolve_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    try:
        return p.resolve(strict=False)
    except OSError:
        return Path(os.path.normpath(str(p.absolute())))


class ProjectDir(QObject):
    root_changed = Signal(str)

    _instance: ProjectDir | None = None

    def __init__(self) -> None:
        super().__init__()
        self._root = ""

    @classmethod
    def instance(cls) -> ProjectDir:
        if cls._instance is None:
            cls._instance = ProjectDir()
        return cls._instance

    def initialize(self, dialog_parent: QWidget | None = None) -> None:
        settings = QSettings(ORG, APP)
        root = str(settings.value(ROOT_KEY, "") or "")

        if not root:
            box = QMessageBox(dialog_parent)
            box.setWindowTitle("Choose Project Folder")
            box.setText(
                "NeuroTendrils keeps your plans, datasets, models, runs, and "
                "lessons together in one project folder."
            )
            box.setInformativeText(
                f"Use the default folder {default_root()}, or choose another location."
            )
            use_default = box.addButton("Use Default", QMessageBox.ButtonRole.AcceptRole)
            choose = box.addButton("Choose…", QMessageBox.ButtonRole.ActionRole)
            box.setDefaultButton(use_default)  # type: ignore[arg-type]
            box.exec()

            root = str(default_root())
            if box.clickedButton() is choose:
                picked = QFileDialog.getExistingDirectory(
                    dialog_parent, "Choose Project Folder", str(Path.home())
                )
                if picked:
                    root = picked
            settings.setValue(ROOT_KEY, root)

        self.set_root(root, persist=False, dialog_parent=dialog_parent)

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
        except OSError:
            if dialog_parent is not None:
                QMessageBox.warning(
                    dialog_parent,
                    "Project Folder Unavailable",
                    f"The project folder {root} could not be created. "
                    "Please choose a different location in Settings.",
                )
        if persist:
            QSettings(ORG, APP).setValue(ROOT_KEY, root)
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

    def learn_dir(self) -> Path:
        return Path(self._root) / "learn"

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
        """Resolve *path* and require it stays inside the project root.

        Uses realpath so symlink write-through outside the project is rejected.
        """
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

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils import __version__
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.core.theme import Theme, ThemeMode


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(640, 420)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget(self)
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(180)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 20, 16, 16)
        nav_title = QLabel("Settings", sidebar)
        nav_title.setObjectName("settingsNavTitle")
        self._nav = QListWidget(sidebar)
        self._nav.setObjectName("settingsNav")
        self._nav.addItems(["Appearance", "Info", "Project"])
        side.addWidget(nav_title)
        side.addWidget(self._nav, 1)

        content = QWidget(self)
        content_l = QVBoxLayout(content)
        content_l.setContentsMargins(24, 20, 24, 16)
        self._stack = QStackedWidget(content)
        self._stack.addWidget(self._appearance_pane())
        self._stack.addWidget(self._info_pane())
        self._stack.addWidget(self._project_pane())
        done = QPushButton("Done", content)
        done.setObjectName("primaryButton")
        done.clicked.connect(self.accept)
        content_l.addWidget(self._stack, 1)
        content_l.addWidget(done, alignment=Qt.AlignmentFlag.AlignRight)

        root.addWidget(sidebar)
        root.addWidget(content, 1)
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)

    def _appearance_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        title = QLabel("Appearance", pane)
        title.setObjectName("settingTitle")
        desc = QLabel("Choose light, dark, or follow the system.", pane)
        desc.setObjectName("settingDescription")
        layout.addWidget(title)
        layout.addWidget(desc)
        row = QHBoxLayout()
        for mode, label in (
            (ThemeMode.LIGHT, "Light"),
            (ThemeMode.DARK, "Dark"),
            (ThemeMode.SYSTEM, "Auto"),
        ):
            btn = QPushButton(label, pane)
            btn.setObjectName("secondaryButton")
            btn.clicked.connect(lambda _=False, m=mode: Theme.instance().set_mode(m))
            row.addWidget(btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return pane

    def _info_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        title = QLabel("Info", pane)
        title.setObjectName("settingTitle")
        layout.addWidget(title)
        self._info_label = QLabel(pane)
        self._info_label.setObjectName("settingDescription")
        self._info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)
        layout.addStretch(1)
        self._refresh_info()
        ProjectDir.instance().root_changed.connect(lambda *_: self._refresh_info())
        return pane

    def _refresh_info(self) -> None:
        project = ProjectDir.instance()
        self._info_label.setText(
            "\n".join(
                [
                    f"App version: {__version__}",
                    f"Project: {project.root or '(not set)'}",
                    f"Python: {sys.executable}",
                    f"{sys.version.split()[0]}",
                    "Workers run in-process (no JSONL IPC).",
                ]
            )
        )

    def _project_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        title = QLabel("Project folder", pane)
        title.setObjectName("settingTitle")
        desc = QLabel(
            "Plans, datasets, models, and runs stay inside this folder.",
            pane,
        )
        desc.setObjectName("settingDescription")
        self._project_path = QLabel(ProjectDir.instance().root, pane)
        self._project_path.setObjectName("filePathLabel")
        self._project_path.setWordWrap(True)
        change = QPushButton("Change project folder…", pane)
        change.setObjectName("secondaryButton")
        change.clicked.connect(self._change_project)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self._project_path)
        layout.addWidget(change, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        ProjectDir.instance().root_changed.connect(self._project_path.setText)
        return pane

    def _change_project(self) -> None:
        start = ProjectDir.instance().root or str(Path.home())
        picked = QFileDialog.getExistingDirectory(self, "Choose Project Folder", start)
        if not picked:
            return
        reply = QMessageBox.question(
            self,
            "Change project folder",
            f"Use {picked} as the project folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            ProjectDir.instance().set_root(picked, persist=True, dialog_parent=self)

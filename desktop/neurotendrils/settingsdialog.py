from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils import __version__
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.core.theme import Theme, ThemeMode
from neurotendrils.widgets.modals import confirm
from neurotendrils.widgets.theme_preview_card import Preview, ThemePreviewCard

_SECTIONS = ("Account", "Appearance", "Storage", "Info")


class SettingsPanel(QWidget):
    """Settings UI presented inside ModalHost (not a separate window)."""

    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setMinimumSize(680, 420)
        self._light_card: ThemePreviewCard | None = None
        self._dark_card: ThemePreviewCard | None = None
        self._auto_card: ThemePreviewCard | None = None

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
        self._nav.addItems(list(_SECTIONS))
        side.addWidget(nav_title)
        side.addWidget(self._nav, 1)

        content = QWidget(self)
        content_l = QVBoxLayout(content)
        content_l.setContentsMargins(24, 20, 24, 16)
        self._stack = QStackedWidget(content)
        self._stack.addWidget(self._account_pane())
        self._stack.addWidget(self._appearance_pane())
        self._stack.addWidget(self._storage_pane())
        self._stack.addWidget(self._info_pane())
        done = QPushButton("Done", content)
        done.setObjectName("primaryButton")
        done.clicked.connect(self.closed.emit)
        content_l.addWidget(self._stack, 1)
        content_l.addWidget(done, alignment=Qt.AlignmentFlag.AlignRight)

        root.addWidget(sidebar)
        root.addWidget(content, 1)
        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.setCurrentRow(0)
        Theme.instance().changed.connect(self._sync_theme_cards)
        self._sync_theme_cards()

    def show_section(self, name: str) -> None:
        try:
            index = _SECTIONS.index(name)
        except ValueError:
            return
        self._nav.setCurrentRow(index)

    def _account_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setSpacing(10)
        title = QLabel("Account", pane)
        title.setObjectName("pageTitle")
        name = QLabel("Guest", pane)
        name.setObjectName("settingTitle")
        blurb = QLabel(
            "You're using NeuroTendrils locally as a guest. "
            "Cloud accounts and sync aren't enabled in this build — "
            "projects stay under your workspace on this machine.",
            pane,
        )
        blurb.setObjectName("settingDescription")
        blurb.setWordWrap(True)
        status = QLabel("Status  ·  Offline", pane)
        status.setObjectName("settingDescription")
        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(name)
        layout.addWidget(blurb)
        layout.addSpacing(12)
        layout.addWidget(status)
        layout.addStretch(1)
        return pane

    def _appearance_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)

        title = QLabel("Appearance", pane)
        title.setObjectName("pageTitle")
        theme_label = QLabel("Theme", pane)
        theme_label.setObjectName("groupLabel")

        self._light_card = ThemePreviewCard(Preview.LIGHT, "Light", pane)
        self._dark_card = ThemePreviewCard(Preview.DARK, "Dark", pane)
        self._auto_card = ThemePreviewCard(Preview.AUTO, "Auto", pane)

        cards = QWidget(pane)
        row = QHBoxLayout(cards)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        row.addWidget(self._light_card)
        row.addWidget(self._dark_card)
        row.addWidget(self._auto_card)
        row.addStretch(1)

        def _select(mode: ThemeMode):
            def _on(_checked: bool = False) -> None:
                Theme.instance().set_mode(mode)
                self._sync_theme_cards()

            return _on

        self._light_card.clicked.connect(_select(ThemeMode.LIGHT))
        self._dark_card.clicked.connect(_select(ThemeMode.DARK))
        self._auto_card.clicked.connect(_select(ThemeMode.SYSTEM))
        self._sync_theme_cards()

        layout.addWidget(title)
        layout.addSpacing(20)
        layout.addWidget(theme_label)
        layout.addSpacing(10)
        layout.addWidget(cards)
        layout.addStretch(1)
        return pane

    def _sync_theme_cards(self) -> None:
        mode = Theme.instance().mode
        if self._light_card is None or self._dark_card is None or self._auto_card is None:
            return
        self._light_card.setChecked(mode is ThemeMode.LIGHT)
        self._dark_card.setChecked(mode is ThemeMode.DARK)
        self._auto_card.setChecked(mode is ThemeMode.SYSTEM)

    def _info_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        title = QLabel("Info", pane)
        title.setObjectName("settingTitle")
        layout.addWidget(title)
        self._info_label = QLabel(pane)
        self._info_label.setObjectName("settingDescription")
        self._info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)
        layout.addStretch(1)
        self._refresh_info()
        ProjectDir.instance().root_changed.connect(lambda *_: self._refresh_info())
        ProjectDir.instance().workspace_changed.connect(lambda *_: self._refresh_info())
        return pane

    def _refresh_info(self) -> None:
        project = ProjectDir.instance()
        self._info_label.setText(
            "\n".join(
                [
                    f"App version: {__version__}",
                    f"Workspace: {project.workspace or '(not set)'}",
                    f"Open project: {project.root or '(not set)'}",
                    f"Python: {sys.executable}",
                    f"{sys.version.split()[0]}",
                    "Workers run in-process (no JSONL IPC).",
                ]
            )
        )

    def _storage_pane(self) -> QWidget:
        pane = QWidget(self)
        layout = QVBoxLayout(pane)
        layout.setSpacing(10)

        title = QLabel("Storage", pane)
        title.setObjectName("settingTitle")
        desc = QLabel(
            "All projects live under the workspace (default ~/NeuroTendrils). "
            "Each project is its own folder. Switch projects from the top-bar "
            "name or the Projects page. “Browse folder” opens the current "
            "project in your file manager.",
            pane,
        )
        desc.setObjectName("settingDescription")
        desc.setWordWrap(True)

        workspace_label = QLabel("Workspace", pane)
        workspace_label.setObjectName("groupLabel")
        self._workspace_path = QLabel(ProjectDir.instance().workspace, pane)
        self._workspace_path.setObjectName("filePathLabel")
        self._workspace_path.setWordWrap(True)
        change_ws = QPushButton("Change workspace…", pane)
        change_ws.setObjectName("secondaryButton")
        change_ws.clicked.connect(self._change_workspace)

        project_label = QLabel("Open project", pane)
        project_label.setObjectName("groupLabel")
        self._project_path = QLabel(ProjectDir.instance().root, pane)
        self._project_path.setObjectName("filePathLabel")
        self._project_path.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addSpacing(8)
        layout.addWidget(workspace_label)
        layout.addWidget(self._workspace_path)
        layout.addWidget(change_ws, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(12)
        layout.addWidget(project_label)
        layout.addWidget(self._project_path)
        layout.addStretch(1)

        ProjectDir.instance().workspace_changed.connect(self._workspace_path.setText)
        ProjectDir.instance().root_changed.connect(self._project_path.setText)
        return pane

    def _change_workspace(self) -> None:
        start = ProjectDir.instance().workspace or str(Path.home())
        picked = QFileDialog.getExistingDirectory(self, "Choose Workspace Folder", start)
        if not picked:
            return
        if confirm(
            self,
            "Change workspace",
            f"Use {picked} as the workspace for all projects?",
            default_yes=True,
        ):
            project = ProjectDir.instance()
            project.set_workspace(picked, persist=True, dialog_parent=self)
            projects = project.list_projects()
            default = Path(picked) / "Default"
            if default.is_dir():
                project.set_root(str(default), persist=True, dialog_parent=self)
            elif projects:
                project.set_root(projects[0].path, persist=True, dialog_parent=self)
            else:
                created = project.create_project("Default", dialog_parent=self)
                if created:
                    project.set_root(created, persist=True, dialog_parent=self)


SettingsDialog = SettingsPanel

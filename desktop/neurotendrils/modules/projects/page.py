"""Projects: grid of project folders under the workspace, then project interior."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QDesktopServices, QMouseEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.dataset_actions import prompt_and_create_dataset
from neurotendrils.core.dataset_io import import_recording
from neurotendrils.core.eeg_formats import import_file_filter, import_format_hint
from neurotendrils.core.formatting import format_bytes, format_relative
from neurotendrils.core.library import (
    LibraryBus,
    LibraryEntry,
    notify_library_changed,
    scan_all,
)
from neurotendrils.core.library_ops import delete_entry, delete_project, rename_entry, rename_project
from neurotendrils.core.notifications import notify
from neurotendrils.core.projectdir import ProjectDir, ProjectInfo
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.modals import alert, confirm, prompt_text
from neurotendrils.widgets.rows import ListRow, RowList
from neurotendrils.widgets.scroll_page import ScrollPage
from neurotendrils.widgets.section import SectionHeader

_RECENT_LIMIT = 8
_GRID = "grid"
_INTERIOR = "interior"


class _ProjectCard(QFrame):
    activated = Signal()
    renameRequested = Signal()
    deleteRequested = Signal()
    browseRequested = Signal()

    def __init__(self, info: ProjectInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._info = info
        self.setObjectName("projectCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(148)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(8)

        name = QLabel(info.name, self)
        name.setObjectName("projectCardTitle")
        name.setWordWrap(True)
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        counts = info.counts
        summary = (
            f"{counts.get('datasets', 0)} datasets  ·  "
            f"{counts.get('runs', 0)} runs  ·  "
            f"{counts.get('models', 0)} models"
        )
        meta = QLabel(summary, self)
        meta.setObjectName("projectCardMeta")
        meta.setWordWrap(True)
        meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        age = QLabel(format_relative(info.modified), self)
        age.setObjectName("projectCardAge")
        age.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(name)
        layout.addWidget(meta)
        layout.addStretch(1)
        layout.addWidget(age)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def _menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        open_act = QAction("Open", menu)
        open_act.triggered.connect(self.activated.emit)
        rename_act = QAction("Rename…", menu)
        rename_act.triggered.connect(self.renameRequested.emit)
        browse_act = QAction("Browse folder…", menu)
        browse_act.triggered.connect(self.browseRequested.emit)
        delete_act = QAction("Delete…", menu)
        delete_act.triggered.connect(self.deleteRequested.emit)
        menu.addAction(open_act)
        menu.addAction(rename_act)
        menu.addAction(browse_act)
        menu.addSeparator()
        menu.addAction(delete_act)
        menu.exec(self.mapToGlobal(pos))


class ProjectsPage(QWidget):
    """Folder grid of projects; open one to manage its datasets / runs / …"""

    openFlowRequested = Signal()
    openStudioRequested = Signal()
    openRunRequested = Signal(str)
    openDatasetRequested = Signal(str)
    openTemplateRequested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._query = ""
        self._index: dict[str, list[LibraryEntry]] | None = None
        self._mode = _GRID

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        self._grid_page = self._build_grid()
        self._interior_page = self._build_interior()
        self._stack.addWidget(self._grid_page)
        self._stack.addWidget(self._interior_page)
        root.addWidget(self._stack)

        ProjectDir.instance().workspace_changed.connect(lambda *_: self.refresh_grid())
        ProjectDir.instance().root_changed.connect(lambda *_: self._on_root_changed())
        LibraryBus.instance().changed.connect(self._on_library_changed)

    # ---------- grid ----------

    def _build_grid(self) -> QWidget:
        page = ScrollPage(self)
        layout = page.content_layout

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(16)
        heading = QVBoxLayout()
        heading.setSpacing(4)
        title = QLabel("Projects", page)
        title.setObjectName("pageTitle")
        self._workspace_label = QLabel("", page)
        self._workspace_label.setObjectName("pageDescription")
        self._workspace_label.setWordWrap(True)
        heading.addWidget(title)
        heading.addWidget(self._workspace_label)
        header.addLayout(heading, 1)

        new_btn = QPushButton("New", page)
        new_btn.setObjectName("primaryButton")
        new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        new_btn.clicked.connect(self.create_project)
        header.addWidget(new_btn, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        layout.addSpacing(16)

        self._grid_search = QLineEdit(page)
        self._grid_search.setObjectName("searchField")
        self._grid_search.setPlaceholderText("Search projects")
        self._grid_search.setClearButtonEnabled(True)
        self._grid_search.setFixedHeight(34)
        self._grid_search.setMaximumWidth(320)
        self._grid_search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._grid_search.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self._grid_search.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._grid_search.setTextMargins(0, 0, 0, 0)
        self._grid_search.textChanged.connect(self._on_grid_query)
        layout.addWidget(self._grid_search)
        layout.addSpacing(20)

        self._cards_host = QWidget(page)
        self._cards = QGridLayout(self._cards_host)
        self._cards.setContentsMargins(0, 0, 0, 0)
        self._cards.setHorizontalSpacing(16)
        self._cards.setVerticalSpacing(16)
        layout.addWidget(self._cards_host)
        layout.addStretch(1)
        return page

    def _on_grid_query(self, text: str) -> None:
        self._query = text.strip()
        self.refresh_grid()

    def set_query(self, query: str) -> None:
        """Top-bar search while on the grid filters project names."""
        if self._mode == _GRID:
            self._grid_search.setText(query)
        else:
            # Interior: filter section lists via simple substring on titles.
            self._interior_query = query.strip().lower()
            self._render_interior()

    def create_project(self) -> None:
        name, ok = prompt_text(
            self, "New project", "Project name:", "Untitled Project"
        )
        if not ok:
            return
        name = (name or "").strip() or "Untitled Project"
        path = ProjectDir.instance().create_project(name, dialog_parent=self)
        if not path:
            return
        self.open_project(path)

    def open_project(self, path: str) -> None:
        ProjectDir.instance().set_root(path, persist=True, dialog_parent=self)
        self.show_interior()

    def show_grid(self) -> None:
        self._mode = _GRID
        self._stack.setCurrentWidget(self._grid_page)
        self.refresh_grid()

    def show_interior(self) -> None:
        self._mode = _INTERIOR
        self._stack.setCurrentWidget(self._interior_page)
        self.refresh_interior(force=True)

    def refresh_grid(self) -> None:
        project = ProjectDir.instance()
        self._workspace_label.setText(
            f"Stored in {project.workspace or '—'}. Open a project to work inside it."
        )
        while self._cards.count():
            item = self._cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        projects = project.list_projects()
        needle = self._query.lower()
        if needle:
            projects = [p for p in projects if needle in p.name.lower()]

        if not projects:
            empty = QLabel(
                "No projects yet. Click New to create one."
                if not needle
                else f"No projects match “{self._query}”.",
                self._cards_host,
            )
            empty.setObjectName("pageDescription")
            empty.setWordWrap(True)
            self._cards.addWidget(empty, 0, 0)
            return

        columns = 2
        for index, info in enumerate(projects):
            card = _ProjectCard(info, self._cards_host)
            card.activated.connect(lambda p=info.path: self.open_project(p))
            card.renameRequested.connect(lambda p=info: self.rename_project(p))
            card.deleteRequested.connect(lambda p=info: self.delete_project(p))
            card.browseRequested.connect(
                lambda p=info.path: QDesktopServices.openUrl(QUrl.fromLocalFile(p))
            )
            self._cards.addWidget(card, index // columns, index % columns)

    # ---------- interior ----------

    def _build_interior(self) -> QWidget:
        page = ScrollPage(self)
        layout = page.content_layout
        self._interior_query = ""

        header = QHBoxLayout()
        header.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(4)

        back_row = QHBoxLayout()
        back_row.setSpacing(8)
        back = QPushButton("← Projects", page)
        back.setObjectName("ghostButton")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        back.clicked.connect(self.show_grid)
        back_row.addWidget(back, 0, Qt.AlignmentFlag.AlignLeft)
        back_row.addStretch(1)
        left.addLayout(back_row)

        self._project_title = QLabel("", page)
        self._project_title.setObjectName("pageTitle")
        self._path_label = QLabel("", page)
        self._path_label.setObjectName("pageDescription")
        self._path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._path_label.setWordWrap(True)
        left.addWidget(self._project_title)
        left.addWidget(self._path_label)
        header.addLayout(left, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        import_btn = QPushButton("Import dataset", page)
        import_btn.setObjectName("primaryButton")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        import_btn.clicked.connect(self.import_dataset)
        folder_btn = QPushButton("Browse folder", page)
        folder_btn.setObjectName("secondaryButton")
        folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        folder_btn.clicked.connect(self._open_folder)
        rename_btn = QPushButton("Rename", page)
        rename_btn.setObjectName("ghostButton")
        rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rename_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        rename_btn.clicked.connect(self._rename_active_project)
        delete_btn = QPushButton("Delete", page)
        delete_btn.setObjectName("ghostButton")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        delete_btn.clicked.connect(self._delete_active_project)
        actions.addWidget(import_btn)
        actions.addWidget(folder_btn)
        actions.addWidget(rename_btn)
        actions.addWidget(delete_btn)
        header.addLayout(actions, 0)
        layout.addLayout(header)
        layout.addSpacing(8)

        hint = QLabel(
            "Datasets, pipelines, runs, templates, and models for this project.",
            page,
        )
        hint.setObjectName("pageDescription")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addSpacing(20)

        self._sections: dict[str, RowList] = {}
        for label, key, glyph, action, slot in (
            (
                "Datasets",
                "datasets",
                Glyph.DATASETS,
                "Create dataset",
                self.create_lab_dataset,
            ),
            ("Pipelines", "plans", Glyph.PROJECTS, "Open NeuroFlow", self.openFlowRequested.emit),
            ("Templates", "templates", Glyph.STUDIO, "Open NeuroStudio", self.openStudioRequested.emit),
            ("Runs", "runs", Glyph.RUNS, "Open NeuroFlow", self.openFlowRequested.emit),
            ("Models", "models", Glyph.MODELS, "Open NeuroStudio", self.openStudioRequested.emit),
        ):
            layout.addWidget(self._build_section(label, key, glyph, action, slot))
        layout.addStretch(1)
        return page

    def _build_section(
        self, label: str, index_key: str, glyph: Glyph, action: str, slot
    ) -> QWidget:
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        header = SectionHeader(label, action, host)
        header.actionTriggered.connect(slot)
        rows = RowList(host)
        rows.setProperty("_ntGlyph", glyph)
        self._sections[index_key] = rows
        layout.addWidget(header)
        layout.addWidget(rows)
        layout.addSpacing(16)
        return host

    def refresh_interior(self, *, force: bool = False) -> None:
        if force or self._index is None:
            self._index = scan_all()
        root = ProjectDir.instance().root
        self._project_title.setText(Path(root).name if root else "No project")
        self._path_label.setText(root or "Open a project from the grid.")
        self._render_interior()

    def _render_interior(self) -> None:
        index = self._index or {
            "plans": [],
            "datasets": [],
            "models": [],
            "runs": [],
            "templates": [],
        }
        empty = {
            "datasets": "No datasets yet. Create a multi-file dataset or import a recording.",
            "plans": "No saved pipelines yet. Build one in NeuroFlow, then Save plan.",
            "templates": "No saved templates yet. Tune one in NeuroStudio and Save template.",
            "runs": "No runs yet. A run is one NeuroFlow plan execution.",
            "models": "No models yet. Train and export one in NeuroStudio.",
        }
        needle = getattr(self, "_interior_query", "") or ""
        for index_key, rows in self._sections.items():
            rows.clear()
            entries = sorted(
                index.get(index_key, []), key=lambda e: e.modified, reverse=True
            )
            if needle:
                entries = [
                    e
                    for e in entries
                    if needle in e.title.lower() or needle in e.subtitle.lower()
                ]
            entries = entries[:_RECENT_LIMIT]
            if not entries:
                rows.add_placeholder(empty[index_key])
                continue
            glyph = rows.property("_ntGlyph")
            for entry in entries:
                row = ListRow(
                    entry.title,
                    entry.subtitle,
                    f"{format_bytes(entry.size_bytes)}   ·   {format_relative(entry.modified)}",
                    glyph if isinstance(glyph, Glyph) else None,
                    rows,
                )
                row.activated.connect(lambda e=entry: self._on_entry_activated(e))
                row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                row.customContextMenuRequested.connect(
                    lambda pos, e=entry, r=row: self._entry_menu(e, r.mapToGlobal(pos))
                )
                rows.add_row(row)

    def _entry_menu(self, entry: LibraryEntry, global_pos: QPoint) -> None:
        menu = QMenu(self)
        open_act = QAction("Open", menu)
        open_act.triggered.connect(lambda: self._on_entry_activated(entry))
        rename_act = QAction("Rename…", menu)
        rename_act.triggered.connect(lambda: self._rename_entry(entry))
        browse_act = QAction("Browse folder…", menu)
        browse_act.triggered.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(Path(entry.path) if Path(entry.path).is_dir() else Path(entry.path).parent)
                )
            )
        )
        delete_act = QAction("Delete…", menu)
        delete_act.triggered.connect(lambda: self._delete_entry(entry))
        menu.addAction(open_act)
        menu.addAction(rename_act)
        menu.addAction(browse_act)
        menu.addSeparator()
        menu.addAction(delete_act)
        menu.exec(global_pos)

    def _rename_entry(self, entry: LibraryEntry) -> None:
        name, ok = prompt_text(self, "Rename", "New name:", entry.title)
        if not ok or not (name or "").strip():
            return
        try:
            rename_entry(entry, name.strip())
        except (OSError, PermissionError, FileNotFoundError, ValueError) as exc:
            alert(self, "Rename failed", str(exc))
            return
        notify_library_changed()
        notify("Renamed", name.strip(), level="info")
        self.refresh_interior(force=True)

    def _delete_entry(self, entry: LibraryEntry) -> None:
        if not confirm(
            self,
            "Delete",
            f"Delete “{entry.title}”? This cannot be undone.",
            default_yes=False,
        ):
            return
        try:
            delete_entry(entry)
        except (OSError, PermissionError, FileNotFoundError) as exc:
            alert(self, "Delete failed", str(exc))
            return
        notify_library_changed()
        notify("Deleted", entry.title, level="info")
        self.refresh_interior(force=True)

    def rename_project(self, info: ProjectInfo) -> None:
        name, ok = prompt_text(self, "Rename project", "Project name:", info.name)
        if not ok or not (name or "").strip():
            return
        try:
            rename_project(info.path, name.strip())
        except (OSError, PermissionError, FileNotFoundError, ValueError) as exc:
            alert(self, "Rename failed", str(exc))
            return
        notify("Project renamed", name.strip(), level="info")
        self.refresh_grid()
        if self._mode == _INTERIOR:
            self.refresh_interior(force=True)

    def delete_project(self, info: ProjectInfo) -> None:
        if not confirm(
            self,
            "Delete project",
            f"Delete project “{info.name}” and all of its files? This cannot be undone.",
            default_yes=False,
        ):
            return
        try:
            delete_project(info.path)
        except (OSError, PermissionError, FileNotFoundError) as exc:
            alert(self, "Delete failed", str(exc))
            return
        notify("Project deleted", info.name, level="info")
        self.show_grid()

    def _rename_active_project(self) -> None:
        root = ProjectDir.instance().root
        if not root:
            return
        info = ProjectInfo(
            name=Path(root).name,
            path=root,
            modified=0,
            counts={},
        )
        for candidate in ProjectDir.instance().list_projects():
            if candidate.path == root:
                info = candidate
                break
        self.rename_project(info)

    def _delete_active_project(self) -> None:
        root = ProjectDir.instance().root
        if not root:
            return
        for candidate in ProjectDir.instance().list_projects():
            if candidate.path == root:
                self.delete_project(candidate)
                return

    def _on_entry_activated(self, entry: LibraryEntry) -> None:
        if entry.kind == "dataset":
            self.openDatasetRequested.emit(entry.path)
        elif entry.kind == "run":
            self.openRunRequested.emit(str(entry.extra.get("output_path") or entry.path))
        elif entry.kind == "plan":
            self.openFlowRequested.emit()
        elif entry.kind == "template":
            self.openTemplateRequested.emit(entry.path)
        elif entry.kind == "model":
            self.openStudioRequested.emit()

    def create_lab_dataset(self) -> None:
        """Create a multi-file lab dataset (project-global entry point)."""
        prompt_and_create_dataset(
            self,
            self,
            after=lambda: self.refresh_interior(force=True),
        )

    def import_dataset(self) -> None:
        """Import a single recording file into the project datasets folder."""
        project = ProjectDir.instance()
        if not project.root:
            alert(self, "Project required", "Open a project first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import recording",
            str(project.datasets_dir()),
            import_file_filter(),
        )
        if not path:
            return
        try:
            dest, copied = import_recording(path)
        except (OSError, ValueError, RuntimeError, FileNotFoundError) as exc:
            alert(self, "Import failed", str(exc))
            return
        notify_library_changed()
        self.refresh_interior(force=True)
        status = "Copied into project" if copied else "Already in project"
        notify("Recording imported", f"{Path(dest).name} · {status}", level="success")
        alert(
            self,
            "Recording ready",
            f"{Path(dest).name}\n{status}\n\n{import_format_hint()}",
        )

    def _open_folder(self) -> None:
        root = ProjectDir.instance().root
        if root:
            QDesktopServices.openUrl(QUrl.fromLocalFile(root))

    # ---------- lifecycle ----------

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        if self._mode == _GRID:
            self.refresh_grid()
        else:
            self.refresh_interior(force=True)

    def _on_root_changed(self) -> None:
        if self._mode == _INTERIOR:
            self.refresh_interior(force=True)
        else:
            self.refresh_grid()

    def _on_library_changed(self) -> None:
        if self._mode == _INTERIOR:
            self.refresh_interior(force=True)
        else:
            self.refresh_grid()

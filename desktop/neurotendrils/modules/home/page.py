"""Home workspace: project at a glance plus recent records."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.formatting import format_bytes, format_relative
from neurotendrils.core.library import LibraryBus, LibraryEntry, scan_all
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.rows import ListRow, RowList
from neurotendrils.widgets.scroll_page import ScrollPage
from neurotendrils.widgets.section import SectionHeader

_RECENT_LIMIT = 4


class _StatBlock(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._value = QLabel("—", self)
        self._value.setObjectName("statValue")
        self._label = QLabel(label, self)
        self._label.setObjectName("statLabel")
        layout.addWidget(self._value)
        layout.addWidget(self._label)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


class HomePage(ScrollPage):
    """Landing workspace; navigation and quick actions are emitted upward."""

    navigateRequested = Signal(str)
    importRequested = Signal()
    trainRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index: dict[str, list[LibraryEntry]] | None = None

        layout = self.content_layout

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(16)
        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(4)
        title = QLabel("Home", self)
        title.setObjectName("pageTitle")
        self._project_label = QLabel("", self)
        self._project_label.setObjectName("pageDescription")
        self._project_label.setWordWrap(True)
        self._project_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        heading.addWidget(title)
        heading.addWidget(self._project_label)
        header.addLayout(heading, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        import_btn = QPushButton("Import recording", self)
        import_btn.setObjectName("primaryButton")
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        import_btn.clicked.connect(self.importRequested.emit)
        train_btn = QPushButton("Train model", self)
        train_btn.setObjectName("secondaryButton")
        train_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        train_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        train_btn.clicked.connect(self.trainRequested.emit)
        folder_btn = QPushButton("Browse folder", self)
        folder_btn.setObjectName("secondaryButton")
        folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        folder_btn.clicked.connect(self._open_project_folder)
        actions.addWidget(import_btn)
        actions.addWidget(train_btn)
        actions.addWidget(folder_btn)
        header.addLayout(actions, 0)
        layout.addLayout(header)
        layout.addSpacing(24)

        layout.addWidget(self._build_stats())
        layout.addSpacing(16)

        self._sections: dict[str, RowList] = {}
        layout.addWidget(
            self._build_section("Recent pipelines", "projects", "plans", Glyph.PROJECTS)
        )
        layout.addWidget(
            self._build_section("Recent datasets", "datasets", "datasets", Glyph.DATASETS)
        )
        layout.addWidget(
            self._build_section("Recent models", "models", "models", Glyph.MODELS)
        )
        layout.addWidget(
            self._build_section("Recent runs", "flow", "runs", Glyph.RUNS)
        )
        layout.addStretch(1)

        project = ProjectDir.instance()
        project.root_changed.connect(lambda *_: self.refresh(force=True))
        LibraryBus.instance().changed.connect(lambda: self.refresh(force=True))
        self._sync_project_label()

    # ---------- construction ----------

    def _build_stats(self) -> QWidget:
        host = QWidget(self)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(32)

        self._stats: dict[str, _StatBlock] = {}
        specs = (
            ("plans", "Pipelines"),
            ("datasets", "Datasets"),
            ("models", "Models"),
            ("storage", "Local storage"),
        )
        for i, (key, label) in enumerate(specs):
            if i:
                divider = QFrame(host)
                divider.setObjectName("statDivider")
                divider.setFrameShape(QFrame.Shape.NoFrame)
                divider.setFixedWidth(1)
                layout.addWidget(divider)
            block = _StatBlock(label, host)
            self._stats[key] = block
            layout.addWidget(block)
        layout.addStretch(1)
        return host

    def _build_section(
        self, label: str, nav_key: str, index_key: str, glyph: Glyph
    ) -> QWidget:
        host = QWidget(self)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = SectionHeader(label, "View all", host)
        header.actionTriggered.connect(
            lambda key=nav_key: self.navigateRequested.emit(key)
        )
        rows = RowList(host)
        rows.setProperty("_ntGlyph", glyph)
        self._sections[index_key] = rows

        layout.addWidget(header)
        layout.addWidget(rows)
        layout.addSpacing(16)
        return host

    # ---------- data ----------

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self.refresh(force=True)

    def refresh(self, *, force: bool = False) -> None:
        if force or self._index is None:
            self._index = scan_all()
        self._sync_project_label()
        self._render()

    def _sync_project_label(self) -> None:
        root = ProjectDir.instance().root
        if not root:
            self._project_label.setText("No project open. Create one under Projects.")
            return
        name = Path(root).name
        self._project_label.setText(f"{name}  ·  {root}")
        self._project_label.setToolTip(root)

    def _render(self) -> None:
        index = self._index or {"plans": [], "datasets": [], "models": [], "runs": []}
        total_bytes = sum(
            entry.size_bytes for entries in index.values() for entry in entries
        )
        self._stats["plans"].set_value(str(len(index.get("plans", []))))
        self._stats["datasets"].set_value(str(len(index.get("datasets", []))))
        self._stats["models"].set_value(str(len(index.get("models", []))))
        self._stats["storage"].set_value(format_bytes(total_bytes))

        for index_key, rows in self._sections.items():
            rows.clear()
            entries = sorted(
                index.get(index_key, []), key=lambda e: e.modified, reverse=True
            )[:_RECENT_LIMIT]
            if not entries:
                rows.add_placeholder(_EMPTY_TEXT[index_key])
                continue
            glyph = rows.property("_ntGlyph")
            for entry in entries:
                row = ListRow(
                    entry.title,
                    entry.subtitle,
                    format_relative(entry.modified),
                    glyph if isinstance(glyph, Glyph) else None,
                    rows,
                )
                row.activated.connect(
                    lambda key=_NAV_FOR_INDEX[index_key]: self.navigateRequested.emit(key)
                )
                rows.add_row(row)

    def _open_project_folder(self) -> None:
        root = ProjectDir.instance().root
        if root:
            QDesktopServices.openUrl(QUrl.fromLocalFile(root))


_EMPTY_TEXT = {
    "plans": "No pipelines yet. Build one in NeuroFlow and save it.",
    "datasets": "No datasets yet. Import a recording to get started.",
    "models": "No models yet. Train one from a prepared dataset.",
    "runs": "No runs yet. A run is one NeuroFlow plan execution.",
}

_NAV_FOR_INDEX = {
    "plans": "flow",
    "datasets": "datasets",
    "models": "models",
    "runs": "flow",
}

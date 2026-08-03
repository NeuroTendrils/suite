"""Library workspace: a filtered record list with a contextual inspector."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.formatting import (
    format_bytes,
    format_number,
    format_path,
    format_relative,
    format_timestamp,
)
from neurotendrils.core.library import (
    LibraryBus,
    LibraryEntry,
    notify_library_changed,
    scan_datasets,
    scan_models,
    scan_plans,
    scan_runs,
    scan_templates,
)
from neurotendrils.core.library_ops import delete_entry, rename_entry
from neurotendrils.core.notifications import notify
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.inspector import INSPECTOR_WIDTH, Inspector
from neurotendrils.widgets.modals import alert, confirm, prompt_text
from neurotendrils.widgets.motion import DURATION_FAST, animate_width
from neurotendrils.widgets.rows import ListRow, RowList
from neurotendrils.widgets.scroll_page import ScrollPage
from neurotendrils.widgets.section import SectionHeader

_SCANNERS = {
    "plan": scan_plans,
    "dataset": scan_datasets,
    "model": scan_models,
    "run": scan_runs,
    "template": scan_templates,
}

_GLYPHS = {
    "plan": Glyph.PROJECTS,
    "dataset": Glyph.DATASETS,
    "model": Glyph.MODELS,
    "run": Glyph.RUNS,
    "template": Glyph.STUDIO,
}

_NOUNS = {
    "plan": ("pipeline", "pipelines"),
    "dataset": ("dataset", "datasets"),
    "model": ("model", "models"),
    "run": ("run", "runs"),
    "template": ("template", "templates"),
}


class LibraryPage(QWidget):
    """List of one record kind, with details in a right-side inspector."""

    primaryActionRequested = Signal()

    def __init__(
        self,
        kind: str,
        title: str,
        description: str,
        primary_action: str = "",
        parent: QWidget | None = None,
        *,
        show_header: bool = True,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._entries: list[LibraryEntry] = []
        self._query = ""
        self._selected: LibraryEntry | None = None
        self._loaded = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._page = ScrollPage(self)
        layout = self._page.content_layout

        if show_header:
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(16)
            heading = QVBoxLayout()
            heading.setContentsMargins(0, 0, 0, 0)
            heading.setSpacing(4)
            title_label = QLabel(title, self)
            title_label.setObjectName("pageTitle")
            description_label = QLabel(description, self)
            description_label.setObjectName("pageDescription")
            heading.addWidget(title_label)
            heading.addWidget(description_label)
            header.addLayout(heading, 1)

            if primary_action:
                action = QPushButton(primary_action, self)
                action.setObjectName("primaryButton")
                action.setCursor(Qt.CursorShape.PointingHandCursor)
                action.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                action.clicked.connect(self.primaryActionRequested.emit)
                header.addWidget(action, 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(header)
            layout.addSpacing(16)

        self._section = SectionHeader(self._count_label(0), "Refresh", self)
        self._section.actionTriggered.connect(lambda: self.refresh(force=True))
        layout.addWidget(self._section)

        self._rows = RowList(self)
        layout.addWidget(self._rows)
        layout.addStretch(1)

        self._inspector = Inspector(self)
        self._inspector.hide()
        self._inspector.closed.connect(self.clear_selection)
        self._inspector.actionTriggered.connect(self._on_inspector_action)

        root.addWidget(self._page, 1)
        root.addWidget(self._inspector, 0)

        ProjectDir.instance().root_changed.connect(lambda *_: self.refresh(force=True))
        LibraryBus.instance().changed.connect(lambda: self.refresh(force=True))

    # ---------- data ----------

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self.refresh(force=True)

    def refresh(self, *, force: bool = False) -> None:
        if force or not self._loaded:
            self._entries = _SCANNERS[self._kind]()
            self._loaded = True
        self._render()

    def set_query(self, query: str) -> None:
        query = query.strip()
        if query == self._query:
            return
        self._query = query
        if self._loaded:
            self._render()

    def clear_selection(self) -> None:
        self._selected = None
        self._rows.select(None)
        if self._inspector.isVisible():
            animate_width(self._inspector, 0, duration=DURATION_FAST).finished.connect(
                self._inspector.hide
            )

    # ---------- rendering ----------

    def _count_label(self, count: int) -> str:
        singular, plural = _NOUNS[self._kind]
        noun = singular if count == 1 else plural
        return f"{count} {noun}"

    def _visible_entries(self) -> list[LibraryEntry]:
        if not self._query:
            return self._entries
        needle = self._query.lower()
        return [
            entry
            for entry in self._entries
            if needle in entry.title.lower() or needle in entry.subtitle.lower()
        ]

    def _render(self) -> None:
        entries = self._visible_entries()
        self._section.set_label(self._count_label(len(entries)))
        self._rows.clear()

        if not entries:
            self._rows.add_placeholder(self._empty_text())
            self.clear_selection()
            return

        glyph = _GLYPHS[self._kind]
        for entry in entries:
            meta = f"{format_bytes(entry.size_bytes)}   ·   {format_relative(entry.modified)}"
            row = ListRow(entry.title, entry.subtitle, meta, glyph, self._rows)
            row.activated.connect(lambda e=entry, r=row: self._select(e, r))
            self._rows.add_row(row)
            if self._selected is not None and entry.path == self._selected.path:
                self._rows.select(row)

    def _empty_text(self) -> str:
        if self._query:
            return f"No matches for “{self._query}”."
        _, plural = _NOUNS[self._kind]
        return f"No {plural} in this project yet."

    def _select(self, entry: LibraryEntry, row: ListRow) -> None:
        self._selected = entry
        self._rows.select(row)
        fields, tips = self._fields(entry)
        self._inspector.set_record(
            self._kind,
            entry.title,
            fields,
            [
                ("rename", "Rename…"),
                ("reveal", "Browse folder"),
                ("copy", "Copy path"),
                ("delete", "Delete…"),
            ],
            tooltips=tips,
        )
        if not self._inspector.isVisible():
            self._inspector.setFixedWidth(0)
            self._inspector.show()
            animate_width(self._inspector, INSPECTOR_WIDTH, duration=DURATION_FAST)

    def _fields(
        self, entry: LibraryEntry
    ) -> tuple[list[tuple[str, str]], dict[str, str]]:
        tips: dict[str, str] = {"Path": entry.path}
        fields: list[tuple[str, str]] = [
            ("Type", entry.subtitle or self._kind.title()),
            ("Size", format_bytes(entry.size_bytes)),
            ("Modified", format_timestamp(entry.modified)),
            ("Path", format_path(entry.path, keep=2)),
        ]
        if self._kind == "plan":
            fields.insert(1, ("Steps", str(entry.extra.get("steps", "—"))))
            dataset_path = str(entry.extra.get("dataset_path") or "")
            if dataset_path:
                inside = ProjectDir.instance().contains(dataset_path)
                fields.append(
                    (
                        "Dataset",
                        format_path(dataset_path, keep=2)
                        if inside
                        else "Outside project folder",
                    )
                )
                if inside:
                    tips["Dataset"] = dataset_path
        if self._kind == "model":
            fields.insert(1, ("Template", str(entry.extra.get("template_id") or "—")))
            fields.insert(2, ("Format", str(entry.extra.get("format") or "—")))
            metrics = entry.extra.get("metrics") or {}
            if metrics:
                fields.append(("Accuracy", format_number(metrics.get("accuracy"))))
                fields.append(
                    ("Balanced accuracy", format_number(metrics.get("balanced_accuracy")))
                )
            publish = entry.extra.get("publish") or {}
            fields.append(("Publish", str(publish.get("status", "local"))))
        if self._kind == "run":
            fields.insert(1, ("Steps", str(entry.extra.get("n_steps", "—"))))
            fields.insert(2, ("Kind", str(entry.extra.get("output_kind") or "—")))
            output = str(entry.extra.get("output_path") or "")
            if output:
                fields.append(("Output", format_path(output, keep=2)))
                tips["Output"] = output
            input_path = str(entry.extra.get("input_path") or "")
            if input_path:
                fields.append(("Input", format_path(input_path, keep=2)))
                tips["Input"] = input_path
        if self._kind == "template":
            fields.insert(1, ("Template", str(entry.extra.get("template_id") or "—")))
            dataset_path = str(entry.extra.get("dataset_path") or "")
            if dataset_path:
                fields.append(("Dataset", format_path(dataset_path, keep=2)))
                tips["Dataset"] = dataset_path
        if not Path(entry.path).exists():
            fields.append(("Status", "Missing on disk"))
        return fields, tips

    def _on_inspector_action(self, key: str) -> None:
        if self._selected is None:
            return
        path = Path(self._selected.path)
        if key == "copy":
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(str(path))
            return
        if key == "reveal":
            target = path if path.is_dir() else path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
            return
        if key == "rename":
            name, ok = prompt_text(self, "Rename", "New name:", self._selected.title)
            if not ok or not (name or "").strip():
                return
            try:
                rename_entry(self._selected, name.strip())
            except (OSError, PermissionError, FileNotFoundError, ValueError) as exc:
                alert(self, "Rename failed", str(exc))
                return
            notify_library_changed()
            notify("Renamed", name.strip(), level="info")
            self.clear_selection()
            self.refresh(force=True)
            return
        if key == "delete":
            title = self._selected.title
            if not confirm(
                self,
                "Delete",
                f"Delete “{title}”? This cannot be undone.",
                default_yes=False,
            ):
                return
            try:
                delete_entry(self._selected)
            except (OSError, PermissionError, FileNotFoundError) as exc:
                alert(self, "Delete failed", str(exc))
                return
            notify_library_changed()
            notify("Deleted", title, level="info")
            self.clear_selection()
            self.refresh(force=True)

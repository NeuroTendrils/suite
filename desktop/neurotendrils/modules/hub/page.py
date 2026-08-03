"""Hub page: local library"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.library import LibraryEntry, scan_all
from neurotendrils.widgets.pageheader import PageHeader
from neurotendrils.widgets.scroll_page import ScrollPage


def _fmt_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024**2:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / 1024**2:.1f} MB"


class HubPage(ScrollPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[LibraryEntry] = []
        self._selected: LibraryEntry | None = None

        self.content_layout.addWidget(
            PageHeader(
                "Hub",
                "Browse local plans, datasets, and models. Cloud sharing comes later.",
            )
        )

        toolbar = QHBoxLayout()
        self._filter = QComboBox(self)
        self._filter.addItems(["All", "Plans", "Datasets", "Models"])
        self._filter.currentTextChanged.connect(lambda *_: self.refresh())
        refresh_btn = QPushButton("Refresh", self)
        refresh_btn.setObjectName("secondaryButton")
        refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self._filter)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch(1)
        self.content_layout.addLayout(toolbar)

        self.content_layout.addWidget(self._label("Local library"))
        self._list_host = QVBoxLayout()
        self._list_host.setSpacing(8)
        list_widget = QWidget(self)
        list_widget.setLayout(self._list_host)
        panel = QFrame(self)
        panel.setObjectName("libraryPanel")
        pl = QVBoxLayout(panel)
        pl.addWidget(list_widget)
        self.content_layout.addWidget(panel)

        self.content_layout.addWidget(self._label("Details"))
        self._detail = QLabel("Select an item to see details.", self)
        self._detail.setObjectName("fileMetaLabel")
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_panel = QFrame(self)
        detail_panel.setObjectName("detailPanel")
        dl = QVBoxLayout(detail_panel)
        dl.addWidget(self._detail)
        actions = QHBoxLayout()
        share = QPushButton("Share")
        share.setObjectName("secondaryButton")
        share.setEnabled(False)
        publish = QPushButton("Publish")
        publish.setObjectName("secondaryButton")
        publish.setEnabled(False)
        actions.addWidget(share)
        actions.addWidget(publish)
        actions.addStretch(1)
        dl.addLayout(actions)
        self.content_layout.addWidget(detail_panel)

        self.content_layout.addWidget(self._label("Cloud"))
        cloud = QLabel(
            "Sign in and cloud storage will appear here. "
            "The Hub website will browse the same library online.",
            self,
        )
        cloud.setObjectName("emptyPanelHint")
        cloud.setWordWrap(True)
        self.content_layout.addWidget(cloud)
        self.content_layout.addStretch(1)
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def _label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("groupLabel")
        return label

    def refresh(self) -> None:
        while self._list_host.count():
            item = self._list_host.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        index = scan_all()
        kind_filter = self._filter.currentText().lower()
        entries: list[LibraryEntry] = []
        if kind_filter in {"all", "plans"}:
            entries.extend(index["plans"])
        if kind_filter in {"all", "datasets"}:
            entries.extend(index["datasets"])
        if kind_filter in {"all", "models"}:
            entries.extend(index["models"])
        self._entries = entries

        if not entries:
            empty = QLabel("No local items yet.", self)
            empty.setObjectName("emptyPanelHint")
            self._list_host.addWidget(empty)
            return

        for entry in entries:
            row = QFrame(self)
            row.setObjectName("libraryRow")
            layout = QHBoxLayout(row)
            text = QVBoxLayout()
            badge = QLabel(entry.kind.upper(), row)
            badge.setObjectName("fileBadge")
            title = QLabel(entry.title, row)
            title.setObjectName("fileNameLabel")
            sub = QLabel(entry.subtitle, row)
            sub.setObjectName("fileMetaLabel")
            text.addWidget(title)
            text.addWidget(sub)
            details = QPushButton("Details", row)
            details.setObjectName("planStepButton")
            details.clicked.connect(lambda _=False, e=entry: self.show_details(e))
            layout.addWidget(badge)
            layout.addLayout(text, 1)
            layout.addWidget(details)
            self._list_host.addWidget(row)

    def show_details(self, entry: LibraryEntry) -> None:
        self._selected = entry
        modified = datetime.fromtimestamp(entry.modified).strftime("%Y-%m-%d %H:%M")
        lines = [
            f"{entry.kind.title()}: {entry.title}",
            f"Path: {entry.path}",
            f"Size: {_fmt_size(entry.size_bytes)}",
            f"Modified: {modified}",
        ]
        if entry.kind == "plan":
            lines.append(f"Steps: {entry.extra.get('steps')}")
            if entry.extra.get("dataset_path"):
                lines.append(f"Dataset: {entry.extra['dataset_path']}")
        if entry.kind == "model":
            lines.append(f"Template: {entry.extra.get('template_id')}")
            lines.append(f"Format: {entry.extra.get('format')}")
            lines.append(f"Artifact: {entry.extra.get('artifact')}")
            metrics = entry.extra.get("metrics") or {}
            if metrics:
                lines.append(
                    f"Accuracy: {metrics.get('accuracy')}  "
                    f"Balanced: {metrics.get('balanced_accuracy')}"
                )
            publish = entry.extra.get("publish") or {}
            lines.append(f"Publish: {publish.get('status', 'local')}")
        # Ensure path exists for display confidence
        if not Path(entry.path).exists():
            lines.append("Warning: path is missing on disk.")
        self._detail.setText("\n".join(lines))

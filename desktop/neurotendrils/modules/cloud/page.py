"""Cloud workspace: sync is not wired up yet, so state this plainly."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from neurotendrils.widgets.rows import hairline
from neurotendrils.widgets.scroll_page import ScrollPage
from neurotendrils.widgets.section import SectionHeader

_PLANNED = (
    ("Sync project", "Mirror pipelines, datasets, and models to your account."),
    ("Share results", "Send a run or model to collaborators with a link."),
    ("Publish models", "Publish a trained model for reuse in other projects."),
)


class CloudPage(ScrollPage):
    connectRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = self.content_layout

        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(4)
        title = QLabel("Cloud", self)
        title.setObjectName("pageTitle")
        description = QLabel(
            "This project is local. Connect an account to sync and share it.",
            self,
        )
        description.setObjectName("pageDescription")
        heading.addWidget(title)
        heading.addWidget(description)
        layout.addLayout(heading)
        layout.addSpacing(16)

        connect_row = QHBoxLayout()
        connect_row.setContentsMargins(0, 0, 0, 0)
        connect = QPushButton("Connect account", self)
        connect.setObjectName("primaryButton")
        connect.setCursor(Qt.CursorShape.PointingHandCursor)
        connect.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        connect.clicked.connect(self.connectRequested.emit)
        connect_row.addWidget(connect)
        connect_row.addStretch(1)
        layout.addLayout(connect_row)
        layout.addSpacing(32)

        layout.addWidget(SectionHeader("Planned", parent=self))
        planned = QWidget(self)
        planned_layout = QVBoxLayout(planned)
        planned_layout.setContentsMargins(0, 0, 0, 0)
        planned_layout.setSpacing(0)
        for i, (name, detail) in enumerate(_PLANNED):
            if i:
                planned_layout.addWidget(hairline(planned))
            planned_layout.addWidget(self._planned_row(name, detail, planned))
        layout.addWidget(planned)
        layout.addStretch(1)

    def _planned_row(self, name: str, detail: str, parent: QWidget) -> QWidget:
        host = QWidget(parent)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(8, 12, 8, 12)
        layout.setSpacing(2)
        title = QLabel(name, host)
        title.setObjectName("rowTitle")
        subtitle = QLabel(detail, host)
        subtitle.setObjectName("rowSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return host

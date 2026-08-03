from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from neurotendrils.widgets.section import eyebrow_font

# Keeps line lengths readable on wide displays instead of stretching edge to edge.
MAX_CONTENT_WIDTH = 1160


class ScrollPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        viewport = QWidget()
        viewport.setObjectName("pageContent")
        viewport_layout = QHBoxLayout(viewport)
        viewport_layout.setContentsMargins(0, 0, 0, 0)
        viewport_layout.setSpacing(0)

        self.content = QWidget(viewport)
        self.content.setObjectName("pageContent")
        self.content.setMaximumWidth(MAX_CONTENT_WIDTH)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(32, 24, 32, 32)
        self.content_layout.setSpacing(16)
        viewport_layout.addWidget(self.content, 1, Qt.AlignmentFlag.AlignTop)
        viewport_layout.addStretch(0)

        scroll.setWidget(viewport)
        outer.addWidget(scroll)

    def section_label(self, text: str) -> QLabel:
        label = QLabel(text.upper(), self)
        label.setObjectName("groupLabel")
        label.setFont(eyebrow_font(label.font()))
        return label

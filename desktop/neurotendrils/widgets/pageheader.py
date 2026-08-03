from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PageHeader(QWidget):
    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(4)
        title_label = QLabel(title, self)
        title_label.setObjectName("pageTitle")
        desc = QLabel(description, self)
        desc.setObjectName("pageDescription")
        desc.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(desc)

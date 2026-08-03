from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget


class SkeletonLoader(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("fingerprintPanel")
        self.setFixedHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

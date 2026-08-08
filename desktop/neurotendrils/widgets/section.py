"""Section header: eyebrow label with an optional trailing action."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


def eyebrow_font(base: QFont) -> QFont:
    font = QFont(base)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
    return font


class SectionHeader(QWidget):
    actionTriggered = Signal()

    def __init__(
        self,
        label: str,
        action: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._label = QLabel(label.upper(), self)
        self._label.setObjectName("sectionLabel")
        self._label.setFont(eyebrow_font(self._label.font()))
        layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)

        self._action: QPushButton | None = None
        if action:
            button = QPushButton(action, self)
            button.setObjectName("ghostButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(self.actionTriggered.emit)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
            self._action = button

    def set_label(self, label: str) -> None:
        self._label.setText(label.upper())

    def set_action_enabled(self, enabled: bool) -> None:
        if self._action is not None:
            self._action.setEnabled(enabled)

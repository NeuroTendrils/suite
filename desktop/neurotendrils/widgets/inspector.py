"""Contextual right-side inspector, shown only when a record is selected."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.widgets.layoututil import clear_layout
from neurotendrils.widgets.rows import hairline
from neurotendrils.widgets.section import eyebrow_font

INSPECTOR_WIDTH = 300


class Inspector(QWidget):
    closed = Signal()
    actionTriggered = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("inspector")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(INSPECTOR_WIDTH)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        heading = QVBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(4)
        self._kind = QLabel("", self)
        self._kind.setObjectName("sectionLabel")
        self._kind.setFont(eyebrow_font(self._kind.font()))
        self._title = QLabel("", self)
        self._title.setObjectName("inspectorTitle")
        self._title.setWordWrap(True)
        heading.addWidget(self._kind)
        heading.addWidget(self._title)
        header.addLayout(heading, 1)

        close = QPushButton("Close", self)
        close.setObjectName("ghostButton")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close.clicked.connect(self.closed.emit)
        header.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        scroll = QScrollArea(self)
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(scroll)
        body.setObjectName("pageContent")
        self._fields = QVBoxLayout(body)
        self._fields.setContentsMargins(0, 4, 0, 0)
        self._fields.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        root.addWidget(hairline(self))

        self._actions_host = QWidget(self)
        self._actions = QVBoxLayout(self._actions_host)
        self._actions.setContentsMargins(0, 4, 0, 0)
        self._actions.setSpacing(6)
        root.addWidget(self._actions_host)

    def set_record(
        self,
        kind: str,
        title: str,
        fields: list[tuple[str, str]],
        actions: list[tuple[str, str]] | None = None,
        *,
        tooltips: dict[str, str] | None = None,
    ) -> None:
        self._kind.setText(kind.upper())
        self._title.setText(title)

        tips = tooltips or {}
        clear_layout(self._fields)
        for key, value in fields:
            self._fields.addWidget(self._field(key, value, tip=tips.get(key, "")))
        self._fields.addStretch(1)

        clear_layout(self._actions)
        for action_key, label in actions or []:
            button = QPushButton(label, self._actions_host)
            button.setObjectName("ghostButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setMinimumHeight(28)
            button.clicked.connect(
                lambda _=False, key=action_key: self.actionTriggered.emit(key)
            )
            self._actions.addWidget(button)

    def _field(self, key: str, value: str, *, tip: str = "") -> QWidget:
        host = QWidget(self)
        host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        key_label = QLabel(key.upper(), host)
        key_label.setObjectName("inspectorKey")
        key_label.setFont(eyebrow_font(key_label.font()))
        value_label = QLabel(value or "—", host)
        value_label.setObjectName("inspectorValue")
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        if tip:
            value_label.setToolTip(tip)
        elif value and len(value) > 40:
            value_label.setToolTip(value)
        layout.addWidget(key_label)
        layout.addWidget(value_label)
        return host

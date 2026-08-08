"""In-window notification list for the top-bar bell."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.formatting import format_relative
from neurotendrils.core.notifications import Notification, NotificationCenter
from neurotendrils.core.theme import Theme
from neurotendrils.widgets.layoututil import clear_layout


class NotificationPanel(QFrame):
    """Child of the shell (not a Qt Popup) so the bell click doesn't dismiss it."""

    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("notificationPanel")
        self.setFixedWidth(320)
        self.setMaximumHeight(420)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

        root = QVBoxLayout(self)
        # Padding leaves room for the painted border + shadow bleed.
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        self._chrome = QWidget(self)
        self._chrome.setObjectName("notificationChrome")
        chrome_l = QVBoxLayout(self._chrome)
        chrome_l.setContentsMargins(0, 0, 0, 0)
        chrome_l.setSpacing(0)

        header = QWidget(self._chrome)
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(14, 12, 10, 8)
        header_l.setSpacing(8)
        title = QLabel("Notifications", header)
        title.setObjectName("notificationTitle")
        clear_btn = QPushButton("Clear", header)
        clear_btn.setObjectName("ghostButton")
        clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear)
        header_l.addWidget(title, 1)
        header_l.addWidget(clear_btn)
        chrome_l.addWidget(header)

        scroll = QScrollArea(self._chrome)
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._body = QWidget(scroll)
        self._list = QVBoxLayout(self._body)
        self._list.setContentsMargins(8, 0, 8, 12)
        self._list.setSpacing(0)
        scroll.setWidget(self._body)
        chrome_l.addWidget(scroll, 1)
        root.addWidget(self._chrome)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

        NotificationCenter.instance().changed.connect(self.refresh)
        Theme.instance().changed.connect(self.update)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        fill = theme.surface_color()
        # Prefer page background so the popover reads as an elevated sheet.
        fill = QColor(theme.colors().background)
        border = theme.border_color()
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(fill)
        painter.drawPath(path)

    def refresh(self) -> None:
        clear_layout(self._list)
        items = NotificationCenter.instance().items()
        if not items:
            empty = QLabel("You're all caught up.", self._body)
            empty.setObjectName("rowSubtitle")
            empty.setContentsMargins(8, 16, 8, 16)
            empty.setWordWrap(True)
            self._list.addWidget(empty)
            self._list.addStretch(1)
            return
        for index, note in enumerate(items):
            self._list.addWidget(self._row(note, last=index == len(items) - 1))
        self._list.addStretch(1)

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        NotificationCenter.instance().mark_all_read()
        self.refresh()

    def _row(self, note: Notification, *, last: bool) -> QWidget:
        row = QFrame(self._body)
        row.setObjectName("notificationRowLast" if last else "notificationRow")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(2)
        title = QLabel(note.title, row)
        title.setObjectName("notificationRowTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        if note.body:
            body = QLabel(note.body, row)
            body.setObjectName("notificationRowBody")
            body.setWordWrap(True)
            layout.addWidget(body)
        meta = QLabel(format_relative(note.created_at), row)
        meta.setObjectName("rowMeta")
        layout.addWidget(meta)
        return row

    def _clear(self) -> None:
        NotificationCenter.instance().clear()

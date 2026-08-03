"""Dropdown results for the top-bar search field."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.search import SearchHit
from neurotendrils.core.theme import Theme
from neurotendrils.widgets.layoututil import clear_layout

_ROW_H = 40
_MAX_VISIBLE = 10
_HEADER_H = 36


class _HitRow(QFrame):
    activated = Signal(object)

    def __init__(self, hit: SearchHit, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hit = hit
        self.setObjectName("searchHitRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(_ROW_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(0)
        self._title = QLabel(hit.title, self)
        self._title.setObjectName("searchHitTitle")
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._meta = QLabel(hit.subtitle or hit.kind, self)
        self._meta.setObjectName("searchHitMeta")
        self._meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text.addWidget(self._title)
        text.addWidget(self._meta)
        layout.addLayout(text, 1)

        kind = QLabel(hit.kind, self)
        kind.setObjectName("searchHitKind")
        kind.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        kind.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(kind, 0)

        self.setToolTip(hit.path)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._hit)
            event.accept()
            return
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        avail = max(80, self.width() - 96)
        self._title.setText(
            self._title.fontMetrics().elidedText(
                self._hit.title, Qt.TextElideMode.ElideMiddle, avail
            )
        )
        self._meta.setText(
            self._meta.fontMetrics().elidedText(
                self._hit.subtitle or self._hit.kind,
                Qt.TextElideMode.ElideMiddle,
                avail,
            )
        )


class SearchPopup(QFrame):
    """Child of the shell so we can align it exactly under the search field."""

    hitActivated = Signal(object)
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("searchPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        self._header = QLabel("", self)
        self._header.setObjectName("searchPopupHeader")
        self._header.setContentsMargins(12, 10, 12, 8)
        root.addWidget(self._header)

        scroll = QScrollArea(self)
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._body = QWidget(scroll)
        self._list = QVBoxLayout(self._body)
        self._list.setContentsMargins(4, 0, 4, 6)
        self._list.setSpacing(1)
        scroll.setWidget(self._body)
        root.addWidget(scroll, 1)
        self._scroll = scroll

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 56))
        self.setGraphicsEffect(shadow)
        Theme.instance().changed.connect(self.update)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        fill = QColor(theme.colors().background)
        border = theme.border_color()
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(fill)
        painter.drawPath(path)

    def set_hits(self, hits: list[SearchHit], *, query: str = "") -> None:
        clear_layout(self._list)
        if not hits:
            self._header.setText("No matches")
            empty = QLabel(
                f"Nothing matched “{query}” in this project."
                if query
                else "No matches in this project.",
                self._body,
            )
            empty.setObjectName("rowSubtitle")
            empty.setWordWrap(True)
            empty.setContentsMargins(10, 8, 10, 14)
            self._list.addWidget(empty)
            self._list.addStretch(1)
            self._fit_height(0)
            return

        shown = hits[:40]
        more = len(hits) - len(shown)
        label = f"{len(shown)} result{'s' if len(shown) != 1 else ''}"
        if more > 0:
            label += f"  ·  +{more} more"
        self._header.setText(label)

        for hit in shown:
            row = _HitRow(hit, self._body)
            row.activated.connect(self.hitActivated.emit)
            self._list.addWidget(row)
        self._list.addStretch(1)
        self._fit_height(len(shown))

    def _fit_height(self, count: int) -> None:
        visible = min(max(count, 1), _MAX_VISIBLE)
        body = visible * _ROW_H + 12
        total = _HEADER_H + body + 4
        self.setFixedHeight(total)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self.width() or 380, self.height() or 280)

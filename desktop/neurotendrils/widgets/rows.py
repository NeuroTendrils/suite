"""Compact list rows: the primary way records are presented."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme
from neurotendrils.widgets.icons import Glyph, single_icon

ROW_HEIGHT = 44


def hairline(parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setObjectName("separator")
    line.setFrameShape(QFrame.Shape.NoFrame)
    line.setFixedHeight(1)
    return line


class ListRow(QWidget):
    """One record: leading glyph, title, subtitle, trailing meta."""

    activated = Signal()

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        meta: str = "",
        glyph: Glyph | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("listRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._glyph = glyph
        self._selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(12)

        self._icon = QLabel(self)
        self._icon.setFixedSize(QSize(18, 18))
        self._icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if glyph is None:
            self._icon.hide()
        layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)

        text_host = QWidget(self)
        text_host.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        text_layout = QVBoxLayout(text_host)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        self._title = QLabel(title, text_host)
        self._title.setObjectName("rowTitle")
        self._subtitle = QLabel(subtitle, text_host)
        self._subtitle.setObjectName("rowSubtitle")
        self._subtitle.setVisible(bool(subtitle))
        text_layout.addWidget(self._title)
        text_layout.addWidget(self._subtitle)
        layout.addWidget(text_host, 1)

        self._meta = QLabel(meta, self)
        self._meta.setObjectName("rowMeta")
        self._meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._meta.setVisible(bool(meta))
        layout.addWidget(self._meta, 0, Qt.AlignmentFlag.AlignVCenter)

        Theme.instance().changed.connect(self._sync_icon)
        self._sync_icon()

    def set_selected(self, selected: bool) -> None:
        if selected == self._selected:
            return
        self._selected = selected
        self.setObjectName("listRowSelected" if selected else "listRow")
        self._title.setObjectName("rowTitleSelected" if selected else "rowTitle")
        for widget in (self, self._title):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def is_selected(self) -> bool:
        return self._selected

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def _sync_icon(self) -> None:
        if self._glyph is None:
            return
        theme = Theme.instance()
        icon = single_icon(self._glyph, theme.muted_text_color(), 18)
        self._icon.setPixmap(icon.pixmap(18, 18))


class RowList(QWidget):
    """Vertical stack of rows separated by hairlines."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("rowList")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._rows: list[ListRow] = []

    def rows(self) -> list[ListRow]:
        return list(self._rows)

    def clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._rows.clear()

    def add_row(self, row: ListRow) -> ListRow:
        if self._rows:
            self._layout.addWidget(hairline(self))
        row.setParent(self)
        self._layout.addWidget(row)
        self._rows.append(row)
        return row

    def add_placeholder(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("rowSubtitle")
        label.setContentsMargins(8, 12, 8, 12)
        label.setWordWrap(True)
        self._layout.addWidget(label)
        return label

    def select(self, row: ListRow | None) -> None:
        for candidate in self._rows:
            candidate.set_selected(candidate is row)

"""Clickable theme preview cards (ported from the C++ ThemePreviewCard)."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QAbstractButton, QWidget

from neurotendrils.core.theme import Theme

_LIGHT_BG = QColor(0xFF, 0xFF, 0xFF)
_LIGHT_BORDER = QColor(0xE8, 0xE9, 0xEC)
_LIGHT_LINE = QColor(0xDE, 0xE0, 0xE4)
_LIGHT_BAR = QColor(0x2F, 0x6F, 0xEB)
_DARK_BG = QColor(0x0F, 0x10, 0x13)
_DARK_BORDER = QColor(0x23, 0x26, 0x2D)
_DARK_LINE = QColor(0x2B, 0x2F, 0x36)
_DARK_BAR = QColor(0x6F, 0x8D, 0xFF)


class Preview(Enum):
    LIGHT = auto()
    DARK = auto()
    AUTO = auto()


class ThemePreviewCard(QAbstractButton):
    def __init__(
        self, preview: Preview, caption: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._preview = preview
        self.setText(caption)
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.sizeHint())
        self.toggled.connect(lambda *_: self.update())
        Theme.instance().changed.connect(self.update)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(168, 140)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = Theme.instance()

        card = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.isChecked():
            tint = theme.accent_color()
            tint.setAlpha(28 if theme.is_dark() else 18)
            painter.setBrush(tint)
            painter.setPen(QPen(theme.accent_color(), 1.6))
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.border_color(), 1.0))
        painter.drawRoundedRect(card, 8.0, 8.0)

        preview = card.adjusted(14.0, 14.0, -14.0, -38.0)
        clip = QPainterPath()
        clip.addRoundedRect(preview, 6.0, 6.0)
        painter.save()
        painter.setClipPath(clip)

        is_dark_preview = self._preview is Preview.DARK
        painter.fillRect(preview, _DARK_BG if is_dark_preview else _LIGHT_BG)

        if self._preview is Preview.AUTO:
            dark_half = QRectF(preview)
            dark_half.setLeft(preview.center().x())
            painter.fillRect(dark_half, _DARK_BG)
            ink = QColor(0xFF, 0xFF, 0xFF)
            self._paint_nt(
                painter,
                QRectF(preview.left() + 10, preview.top() + 12, 22, 22),
                _LIGHT_BAR,
                ink,
            )
            self._paint_nt(
                painter,
                QRectF(preview.center().x() + 10, preview.top() + 12, 22, 22),
                _DARK_BAR,
                ink,
            )
        else:
            bar = _DARK_BAR if is_dark_preview else _LIGHT_BAR
            line = _DARK_LINE if is_dark_preview else _LIGHT_LINE
            ink = QColor(0xFF, 0xFF, 0xFF)
            x = preview.left() + 12.0
            width = preview.width() - 24.0
            self._paint_nt(
                painter,
                QRectF(x, preview.top() + 12.0, 22.0, 22.0),
                bar,
                ink,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(line)
            painter.drawRoundedRect(
                QRectF(x + 30.0, preview.top() + 16.0, width - 30.0, 5.0), 2.5, 2.5
            )
            painter.drawRoundedRect(
                QRectF(x + 30.0, preview.top() + 28.0, (width - 30.0) * 0.7, 5.0),
                2.5,
                2.5,
            )
            painter.drawRoundedRect(
                QRectF(x, preview.top() + 44.0, width * 0.55, 5.0), 2.5, 2.5
            )

        painter.restore()
        border = _DARK_BORDER if self._preview is Preview.DARK else _LIGHT_BORDER
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(preview, 6.0, 6.0)

        caption = QRectF(
            card.left(),
            preview.bottom(),
            card.width(),
            card.bottom() - preview.bottom(),
        )
        font = painter.font()
        font.setBold(self.isChecked())
        painter.setFont(font)
        if self.isChecked():
            painter.setPen(theme.accent_color())
        else:
            painter.setPen(theme.muted_text_color())
        painter.drawText(caption, int(Qt.AlignmentFlag.AlignCenter), self.text())

    @staticmethod
    def _paint_nt(
        painter: QPainter, rect: QRectF, plate: QColor, ink: QColor
    ) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(plate)
        painter.drawRoundedRect(rect, 5.0, 5.0)
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(max(8, int(rect.height() * 0.48)))
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "NT")

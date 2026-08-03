"""Theme-tinted vector glyphs (ported from the C++ icons widget)."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


class Glyph(Enum):
    FLOW = auto()
    STUDIO = auto()
    HUB = auto()
    SETTINGS = auto()
    FILE = auto()


def _paint_glyph(painter: QPainter, glyph: Glyph, color: QColor) -> None:
    # Drawn in a 24×24 logical coordinate space.
    stroke = QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    if glyph is Glyph.FLOW:
        painter.setPen(stroke)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        branches = QPainterPath()
        branches.moveTo(7.8, 12.0)
        branches.lineTo(10.5, 12.0)
        branches.cubicTo(14.0, 12.0, 13.0, 5.5, 16.3, 5.5)
        branches.moveTo(10.5, 12.0)
        branches.cubicTo(14.0, 12.0, 13.0, 18.5, 16.3, 18.5)
        painter.drawPath(branches)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(5.5, 12.0), 2.2, 2.2)
        painter.drawEllipse(QPointF(18.5, 5.5), 2.2, 2.2)
        painter.drawEllipse(QPointF(18.5, 18.5), 2.2, 2.2)
        return

    if glyph is Glyph.STUDIO:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(4.5, 12.0, 3.2, 7.5), 1.4, 1.4)
        painter.drawRoundedRect(QRectF(10.4, 5.0, 3.2, 14.5), 1.4, 1.4)
        painter.drawRoundedRect(QRectF(16.3, 9.0, 3.2, 10.5), 1.4, 1.4)
        return

    if glyph is Glyph.HUB:
        painter.setPen(stroke)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(4.5, 4.5, 6.4, 6.4), 1.8, 1.8)
        painter.drawRoundedRect(QRectF(13.1, 4.5, 6.4, 6.4), 1.8, 1.8)
        painter.drawRoundedRect(QRectF(4.5, 13.1, 6.4, 6.4), 1.8, 1.8)
        painter.drawRoundedRect(QRectF(13.1, 13.1, 6.4, 6.4), 1.8, 1.8)
        return

    if glyph is Glyph.SETTINGS:
        painter.setPen(stroke)
        painter.drawLine(QPointF(4.5, 7.0), QPointF(19.5, 7.0))
        painter.drawLine(QPointF(4.5, 12.0), QPointF(19.5, 12.0))
        painter.drawLine(QPointF(4.5, 17.0), QPointF(19.5, 17.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(9.0, 7.0), 2.3, 2.3)
        painter.drawEllipse(QPointF(15.0, 12.0), 2.3, 2.3)
        painter.drawEllipse(QPointF(7.5, 17.0), 2.3, 2.3)
        return

    if glyph is Glyph.FILE:
        painter.setPen(stroke)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        page = QPainterPath()
        page.moveTo(8.0, 3.5)
        page.lineTo(14.0, 3.5)
        page.lineTo(19.0, 8.5)
        page.lineTo(19.0, 20.5)
        page.cubicTo(19.0, 21.3, 18.3, 22.0, 17.5, 22.0)
        page.lineTo(6.5, 22.0)
        page.cubicTo(5.7, 22.0, 5.0, 21.3, 5.0, 20.5)
        page.lineTo(5.0, 5.0)
        page.cubicTo(5.0, 4.2, 5.7, 3.5, 6.5, 3.5)
        page.closeSubpath()
        painter.drawPath(page)
        painter.drawLine(QPointF(14.0, 3.5), QPointF(14.0, 8.5))
        painter.drawLine(QPointF(14.0, 8.5), QPointF(19.0, 8.5))
        painter.drawLine(QPointF(8.5, 13.0), QPointF(15.5, 13.0))
        painter.drawLine(QPointF(8.5, 16.5), QPointF(15.5, 16.5))


def render_glyph(
    glyph: Glyph, color: QColor, size: int, device_pixel_ratio: float = 1.0
) -> QPixmap:
    pixmap = QPixmap(int(size * device_pixel_ratio), int(size * device_pixel_ratio))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)
    _paint_glyph(painter, glyph, color)
    painter.end()
    return pixmap


def icon(glyph: Glyph, normal: QColor, selected: QColor) -> QIcon:
    result = QIcon()
    for size in (16, 18, 20, 24, 32):
        for dpr in (1.0, 2.0):
            result.addPixmap(
                render_glyph(glyph, normal, size, dpr), QIcon.Mode.Normal
            )
            result.addPixmap(
                render_glyph(glyph, selected, size, dpr), QIcon.Mode.Selected
            )
    return result


def avatar(
    size: int,
    background: QColor,
    foreground: QColor,
    device_pixel_ratio: float = 1.0,
) -> QPixmap:
    pixmap = QPixmap(int(size * device_pixel_ratio), int(size * device_pixel_ratio))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)

    circle = QPainterPath()
    circle.addEllipse(QRectF(0.5, 0.5, 23.0, 23.0))
    painter.setClipPath(circle)
    painter.fillPath(circle, background)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(foreground)
    painter.drawEllipse(QPointF(12.0, 9.6), 3.6, 3.6)

    shoulders = QPainterPath()
    shoulders.addRoundedRect(QRectF(4.8, 15.0, 14.4, 12.0), 6.4, 6.4)
    painter.fillPath(shoulders, foreground)
    painter.end()
    return pixmap

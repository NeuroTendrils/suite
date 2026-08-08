"""Theme-tinted vector glyphs drawn in a 24x24 logical space."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

_STROKE_WIDTH = 1.6


class Glyph(Enum):
    HOME = auto()
    PROJECTS = auto()
    DATASETS = auto()
    MODELS = auto()
    RUNS = auto()
    CLOUD = auto()
    SETTINGS = auto()
    SEARCH = auto()
    NOTIFICATIONS = auto()
    CHEVRON_LEFT = auto()
    CHEVRON_RIGHT = auto()
    FILE = auto()
    # Retained for module pages that still reference the original glyph names.
    FLOW = auto()
    STUDIO = auto()
    HUB = auto()


def _pen(color: QColor) -> QPen:
    return QPen(
        color,
        _STROKE_WIDTH,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )


def _paint_glyph(painter: QPainter, glyph: Glyph, color: QColor) -> None:
    stroke = _pen(color)
    painter.setPen(stroke)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if glyph is Glyph.HOME:
        roof = QPainterPath()
        roof.moveTo(4.0, 10.6)
        roof.lineTo(12.0, 4.2)
        roof.lineTo(20.0, 10.6)
        painter.drawPath(roof)
        painter.drawRoundedRect(QRectF(6.0, 10.4, 12.0, 9.4), 1.8, 1.8)
        painter.drawLine(QPointF(10.4, 19.8), QPointF(10.4, 14.4))
        painter.drawLine(QPointF(13.6, 19.8), QPointF(13.6, 14.4))
        return

    if glyph is Glyph.PROJECTS:
        folder = QPainterPath()
        folder.moveTo(4.2, 7.6)
        folder.lineTo(9.4, 7.6)
        folder.lineTo(11.2, 9.8)
        folder.lineTo(19.8, 9.8)
        folder.lineTo(19.8, 18.4)
        folder.lineTo(4.2, 18.4)
        folder.closeSubpath()
        painter.drawPath(folder)
        return

    if glyph is Glyph.DATASETS:
        painter.drawEllipse(QRectF(4.6, 4.6, 14.8, 4.4))
        arc_left = QPainterPath()
        arc_left.moveTo(4.6, 6.8)
        arc_left.lineTo(4.6, 17.2)
        arc_left.cubicTo(4.6, 18.6, 8.0, 19.4, 12.0, 19.4)
        arc_left.cubicTo(16.0, 19.4, 19.4, 18.6, 19.4, 17.2)
        arc_left.lineTo(19.4, 6.8)
        painter.drawPath(arc_left)
        mid = QPainterPath()
        mid.moveTo(4.6, 12.0)
        mid.cubicTo(4.6, 13.4, 8.0, 14.2, 12.0, 14.2)
        mid.cubicTo(16.0, 14.2, 19.4, 13.4, 19.4, 12.0)
        painter.drawPath(mid)
        return

    if glyph is Glyph.MODELS:
        cube = QPainterPath()
        cube.moveTo(12.0, 3.8)
        cube.lineTo(19.8, 8.0)
        cube.lineTo(19.8, 16.0)
        cube.lineTo(12.0, 20.2)
        cube.lineTo(4.2, 16.0)
        cube.lineTo(4.2, 8.0)
        cube.closeSubpath()
        painter.drawPath(cube)
        painter.drawLine(QPointF(4.2, 8.0), QPointF(12.0, 12.1))
        painter.drawLine(QPointF(19.8, 8.0), QPointF(12.0, 12.1))
        painter.drawLine(QPointF(12.0, 12.1), QPointF(12.0, 20.2))
        return

    if glyph is Glyph.RUNS or glyph is Glyph.FLOW:
        wave = QPainterPath()
        wave.moveTo(3.4, 12.0)
        wave.lineTo(7.0, 12.0)
        wave.lineTo(9.2, 6.6)
        wave.lineTo(12.0, 17.6)
        wave.lineTo(14.6, 9.4)
        wave.lineTo(16.6, 12.0)
        wave.lineTo(20.6, 12.0)
        painter.drawPath(wave)
        return

    if glyph is Glyph.CLOUD:
        cloud = QPainterPath()
        cloud.moveTo(7.6, 17.4)
        cloud.cubicTo(4.6, 17.4, 3.4, 15.4, 3.4, 13.8)
        cloud.cubicTo(3.4, 12.0, 4.8, 10.5, 6.8, 10.4)
        cloud.cubicTo(7.4, 7.6, 9.8, 6.0, 12.4, 6.0)
        cloud.cubicTo(15.4, 6.0, 17.6, 8.2, 17.8, 11.0)
        cloud.cubicTo(19.6, 11.4, 20.6, 12.8, 20.6, 14.3)
        cloud.cubicTo(20.6, 16.0, 19.2, 17.4, 17.0, 17.4)
        cloud.closeSubpath()
        painter.drawPath(cloud)
        return

    if glyph is Glyph.SETTINGS:
        painter.drawLine(QPointF(4.6, 7.4), QPointF(19.4, 7.4))
        painter.drawLine(QPointF(4.6, 12.0), QPointF(19.4, 12.0))
        painter.drawLine(QPointF(4.6, 16.6), QPointF(19.4, 16.6))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QPointF(9.2, 7.4), 2.1, 2.1)
        painter.drawEllipse(QPointF(15.0, 12.0), 2.1, 2.1)
        painter.drawEllipse(QPointF(7.8, 16.6), 2.1, 2.1)
        return

    if glyph is Glyph.SEARCH:
        painter.drawEllipse(QRectF(4.8, 4.8, 11.0, 11.0))
        painter.drawLine(QPointF(14.6, 14.6), QPointF(19.4, 19.4))
        return

    if glyph is Glyph.NOTIFICATIONS:
        bell = QPainterPath()
        bell.moveTo(6.4, 16.4)
        bell.lineTo(6.4, 11.2)
        bell.cubicTo(6.4, 8.0, 8.9, 5.4, 12.0, 5.4)
        bell.cubicTo(15.1, 5.4, 17.6, 8.0, 17.6, 11.2)
        bell.lineTo(17.6, 16.4)
        painter.drawPath(bell)
        painter.drawLine(QPointF(4.8, 16.4), QPointF(19.2, 16.4))
        arc = QPainterPath()
        arc.moveTo(10.2, 18.0)
        arc.cubicTo(10.6, 19.4, 13.4, 19.4, 13.8, 18.0)
        painter.drawPath(arc)
        return

    if glyph is Glyph.CHEVRON_LEFT:
        chevron = QPainterPath()
        chevron.moveTo(14.2, 6.8)
        chevron.lineTo(9.0, 12.0)
        chevron.lineTo(14.2, 17.2)
        painter.drawPath(chevron)
        return

    if glyph is Glyph.CHEVRON_RIGHT:
        chevron = QPainterPath()
        chevron.moveTo(9.8, 6.8)
        chevron.lineTo(15.0, 12.0)
        chevron.lineTo(9.8, 17.2)
        painter.drawPath(chevron)
        return

    if glyph is Glyph.STUDIO:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(4.8, 12.4, 3.0, 7.0), 1.2, 1.2)
        painter.drawRoundedRect(QRectF(10.5, 5.6, 3.0, 13.8), 1.2, 1.2)
        painter.drawRoundedRect(QRectF(16.2, 9.4, 3.0, 10.0), 1.2, 1.2)
        return

    if glyph is Glyph.HUB:
        painter.drawRoundedRect(QRectF(4.8, 4.8, 6.2, 6.2), 1.6, 1.6)
        painter.drawRoundedRect(QRectF(13.0, 4.8, 6.2, 6.2), 1.6, 1.6)
        painter.drawRoundedRect(QRectF(4.8, 13.0, 6.2, 6.2), 1.6, 1.6)
        painter.drawRoundedRect(QRectF(13.0, 13.0, 6.2, 6.2), 1.6, 1.6)
        return

    if glyph is Glyph.FILE:
        page = QPainterPath()
        page.moveTo(7.4, 3.8)
        page.lineTo(13.8, 3.8)
        page.lineTo(18.6, 8.6)
        page.lineTo(18.6, 20.2)
        page.lineTo(5.4, 20.2)
        page.closeSubpath()
        painter.drawPath(page)
        painter.drawLine(QPointF(13.8, 3.8), QPointF(13.8, 8.6))
        painter.drawLine(QPointF(13.8, 8.6), QPointF(18.6, 8.6))
        painter.drawLine(QPointF(8.6, 13.2), QPointF(15.4, 13.2))
        painter.drawLine(QPointF(8.6, 16.4), QPointF(15.4, 16.4))


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
            result.addPixmap(render_glyph(glyph, normal, size, dpr), QIcon.Mode.Normal)
            result.addPixmap(
                render_glyph(glyph, selected, size, dpr), QIcon.Mode.Selected
            )
            result.addPixmap(render_glyph(glyph, selected, size, dpr), QIcon.Mode.Active)
    return result


def single_icon(glyph: Glyph, color: QColor, size: int = 18, dpr: float = 2.0) -> QIcon:
    result = QIcon()
    result.addPixmap(render_glyph(glyph, color, size, dpr))
    return result


def brand_mark(
    size: int,
    background: QColor,
    foreground: QColor,
    device_pixel_ratio: float = 1.0,
) -> QPixmap:
    """Rounded NT badge. *background* is the plate; *foreground* is the letters."""
    pixmap = QPixmap(int(size * device_pixel_ratio), int(size * device_pixel_ratio))
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    rect = QRectF(0.5, 0.5, size - 1.0, size - 1.0)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(rect, size * 0.22, size * 0.22)

    font = painter.font()
    font.setPixelSize(max(8, int(size * 0.42)))
    font.setBold(True)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -0.5)
    painter.setFont(font)
    painter.setPen(foreground)
    painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "NT")
    painter.end()
    return pixmap


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
    painter.drawEllipse(QPointF(12.0, 9.8), 3.4, 3.4)

    shoulders = QPainterPath()
    shoulders.addRoundedRect(QRectF(5.0, 15.2, 14.0, 11.6), 6.2, 6.2)
    painter.fillPath(shoulders, foreground)
    painter.end()
    return pixmap

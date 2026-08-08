"""EEGLAB-style 2D scalp topoplot (QPainter + QImage interpolation)."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from neurotendrils.core.theme import Theme

_GRID = 64
_IDW_POWER = 2.0
_IDW_EPS = 1e-6


def positions_on_circle(n: int, *, radius: float = 0.85) -> list[tuple[float, float]]:
    if n <= 0:
        return []
    return [
        (
            radius * math.cos(2.0 * math.pi * i / n - math.pi / 2.0),
            radius * math.sin(2.0 * math.pi * i / n - math.pi / 2.0),
        )
        for i in range(n)
    ]


def positions_from_info(info: Mapping[str, Any] | Any) -> dict[str, tuple[float, float]]:
    """Extract 2D (x, y) positions from an MNE-style info dict or ch_pos mapping."""
    ch_pos: Mapping[str, Sequence[float]] | None = None
    if isinstance(info, Mapping):
        ch_pos = info.get("ch_pos") or info.get("dig")  # type: ignore[assignment]
        if ch_pos is None and "chs" in info:
            ch_pos = {
                str(ch.get("ch_name", "")): ch.get("loc")[:3]
                for ch in info.get("chs") or []
                if ch.get("loc") is not None
            }
    elif hasattr(info, "get_positions"):
        pos = info.get_positions()
        ch_pos = pos.get("ch_pos") if isinstance(pos, dict) else None
    if not ch_pos:
        return {}
    out: dict[str, tuple[float, float]] = {}
    for name, loc in ch_pos.items():
        if loc is None:
            continue
        seq = list(loc)
        if len(seq) >= 2:
            out[str(name)] = (float(seq[0]), float(seq[1]))
    return out


def _normalize(values: list[float]) -> tuple[list[float], float]:
    if not values:
        return [], 1.0
    peak = max(abs(float(v)) for v in values)
    if peak <= 0:
        return [0.0] * len(values), 1.0
    return [float(v) / peak for v in values], peak


def diverging_color(t: float) -> QColor:
    """Blue (-1) → white (0) → red (+1)."""
    t = max(-1.0, min(1.0, float(t)))
    if t < 0:
        u = t + 1.0
        return QColor(
            int(33 + (247 - 33) * u),
            int(102 + (247 - 102) * u),
            int(172 + (247 - 172) * u),
        )
    u = t
    return QColor(
        int(247 + (178 - 247) * u),
        int(247 + (24 - 247) * u),
        int(247 + (43 - 247) * u),
    )


def _idw_grid(
    values: list[float],
    positions: list[tuple[float, float]],
    size: int = _GRID,
) -> tuple[list[float], float]:
    """Return flattened grid values (row-major) and peak abs for masking."""
    if not values or not positions:
        return [0.0] * (size * size), 1.0
    norm, peak = _normalize(values)
    grid: list[float] = []
    half = (size - 1) / 2.0
    for row in range(size):
        for col in range(size):
            x = (col / half) - 1.0
            y = (row / half) - 1.0
            if x * x + y * y > 1.02:
                grid.append(float("nan"))
                continue
            w_sum = 0.0
            v_sum = 0.0
            for (px, py), val in zip(positions, norm, strict=False):
                d2 = (x - px) ** 2 + (y - py) ** 2
                if d2 < _IDW_EPS:
                    v_sum = val
                    w_sum = 1.0
                    break
                w = 1.0 / (d2 ** (_IDW_POWER / 2.0))
                w_sum += w
                v_sum += w * val
            grid.append(v_sum / w_sum if w_sum > 0 else 0.0)
    return grid, peak


def _grid_to_image(grid: list[float], size: int = _GRID) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    for row in range(size):
        for col in range(size):
            v = grid[row * size + col]
            if v != v:
                img.setPixelColor(col, row, QColor(0, 0, 0, 0))
            else:
                img.setPixelColor(col, row, diverging_color(v))
    return img


class TopoPlot(QWidget):
    """Circular scalp map with interpolated color field."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(96, 96)
        self._title = ""
        self._values: list[float] = []
        self._ch_names: list[str] = []
        self._positions: list[tuple[float, float]] = []
        self._image = QImage()
        Theme.instance().changed.connect(self.update)

    def set_title(self, title: str) -> None:
        self._title = str(title)
        self.update()

    def set_map(
        self,
        values: list[float],
        ch_names: list[str],
        positions: list[tuple[float, float]] | None = None,
    ) -> None:
        self._values = [float(v) for v in values]
        self._ch_names = [str(n) for n in ch_names]
        n = len(self._values)
        if positions is not None and len(positions) >= n:
            self._positions = [(float(p[0]), float(p[1])) for p in positions[:n]]
        else:
            self._positions = positions_on_circle(n)
        grid, _ = _idw_grid(self._values, self._positions)
        self._image = _grid_to_image(grid)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())

        margin = 4
        title_h = 14 if self._title else 0
        side = min(self.width(), self.height() - title_h - margin * 2) - margin * 2
        if side < 8:
            return
        cx = self.width() / 2.0
        cy = margin + title_h + side / 2.0
        r = side / 2.0

        if self._title:
            painter.setPen(theme.muted_text_color())
            font = painter.font()
            font.setPixelSize(10)
            painter.setFont(font)
            painter.drawText(
                0,
                margin,
                self.width(),
                title_h,
                Qt.AlignmentFlag.AlignCenter,
                self._title,
            )

        if self._image.isNull() or not self._values:
            painter.setPen(theme.muted_text_color())
            painter.drawEllipse(int(cx - r), int(cy - r), int(side), int(side))
            painter.drawText(
                int(cx - r),
                int(cy - 6),
                int(side),
                12,
                Qt.AlignmentFlag.AlignCenter,
                "—",
            )
            painter.end()
            return

        # Interpolated field clipped to head circle
        painter.save()
        clip = QPainterPath()
        clip.addEllipse(cx - r, cy - r, side, side)
        painter.setClipPath(clip)
        painter.drawImage(int(cx - r), int(cy - r), self._image.scaled(side, side))
        painter.restore()

        # Head outline
        pen = QPen(theme.text_color(), 1.4)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(cx - r), int(cy - r), int(side), int(side))

        # Nose
        nose_w = r * 0.12
        nose_h = r * 0.08
        nose = QPolygonF(
            [
                QPointF(cx, cy - r - nose_h),
                QPointF(cx - nose_w, cy - r + nose_h * 0.5),
                QPointF(cx + nose_w, cy - r + nose_h * 0.5),
            ]
        )
        painter.drawPolygon(nose)

        # Ears
        ear_w = r * 0.08
        ear_h = r * 0.22
        painter.drawArc(
            int(cx - r - ear_w * 0.6),
            int(cy - ear_h / 2),
            int(ear_w),
            int(ear_h),
            90 * 16,
            180 * 16,
        )
        painter.drawArc(
            int(cx + r - ear_w * 0.4),
            int(cy - ear_h / 2),
            int(ear_w),
            int(ear_h),
            270 * 16,
            180 * 16,
        )

        # Electrode dots
        dot_r = max(2.0, r * 0.035)
        for (px, py), name in zip(self._positions, self._ch_names, strict=False):
            ex = cx + px * r
            ey = cy - py * r
            painter.setPen(QPen(theme.text_color(), 1.0))
            painter.setBrush(theme.text_color())
            painter.drawEllipse(int(ex - dot_r), int(ey - dot_r), int(dot_r * 2), int(dot_r * 2))
            if side >= 120 and len(self._ch_names) <= 32:
                painter.setPen(theme.muted_text_color())
                font = painter.font()
                font.setPixelSize(8)
                painter.setFont(font)
                painter.drawText(int(ex + 3), int(ey + 3), name)

        painter.end()


class TopoPlotPanel(QWidget):
    """TopoPlot with an optional section label (for embedding)."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._label = QLabel(title, self)
        self._label.setObjectName("sectionLabel")
        self._label.setVisible(bool(title))
        layout.addWidget(self._label)
        self.plot = TopoPlot(self)
        layout.addWidget(self.plot, 1)

    def set_title(self, title: str) -> None:
        self._label.setText(title)
        self._label.setVisible(bool(title))
        self.plot.set_title("")

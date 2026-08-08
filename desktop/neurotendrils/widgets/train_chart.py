"""Live training curves drawn with QPainter (no charting dependency)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from neurotendrils.core.theme import Theme


def _finite(values: list[float]) -> list[float]:
    return [v for v in values if v == v]


def _padded_range(
    values: list[float], *, fallback: tuple[float, float]
) -> tuple[float, float]:
    if not values:
        return fallback
    lo, hi = min(values), max(values)
    if hi <= lo:
        span = max(abs(lo) * 0.1, 0.05)
        lo, hi = lo - span, hi + span
    else:
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad
    return lo, hi


class MetricChart(QWidget):
    """One metric (+ optional validation series) against epoch."""

    def __init__(
        self,
        title: str,
        *,
        primary_label: str,
        secondary_label: str,
        fallback_range: tuple[float, float] = (0.0, 1.0),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("trainChart")
        self.setMinimumHeight(140)
        self._title = title
        self._primary_label = primary_label
        self._secondary_label = secondary_label
        self._fallback = fallback_range
        self._epochs: list[int] = []
        self._primary: list[float] = []
        self._secondary: list[float] = []

    def clear(self) -> None:
        self._epochs.clear()
        self._primary.clear()
        self._secondary.clear()
        self.update()

    def add_point(
        self,
        epoch: int,
        primary: float | None = None,
        secondary: float | None = None,
    ) -> None:
        self._epochs.append(int(epoch))
        self._primary.append(float(primary) if primary is not None else float("nan"))
        self._secondary.append(
            float(secondary) if secondary is not None else float("nan")
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        theme = Theme.instance()
        muted = theme.muted_text_color()
        accent = theme.accent_color()
        border = QColor(muted)
        border.setAlpha(60)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(QPen(border, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 6, 6)

        plot = QRectF(rect.adjusted(40, 22, -12, -24))
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)

        # Title
        painter.setPen(muted)
        painter.drawText(
            QRectF(plot.left(), rect.top() + 4, plot.width(), 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._title,
        )

        y_min, y_max = _padded_range(
            _finite(self._primary + self._secondary), fallback=self._fallback
        )
        x0, x1 = plot.left(), plot.right()
        y0, y1 = plot.bottom(), plot.top()

        grid = QColor(border)
        grid.setAlpha(40)
        painter.setPen(QPen(grid, 1, Qt.PenStyle.DotLine))
        for frac in (0.0, 0.5, 1.0):
            y = y0 + (y1 - y0) * frac
            painter.drawLine(int(x0), int(y), int(x1), int(y))

        # Axis ticks — always drawn so the empty chart still reads as a graph.
        painter.setPen(muted)
        painter.drawText(
            QRectF(4, plot.top(), 34, 14),
            Qt.AlignmentFlag.AlignLeft,
            f"{y_max:.2f}",
        )
        painter.drawText(
            QRectF(4, plot.bottom() - 12, 34, 14),
            Qt.AlignmentFlag.AlignLeft,
            f"{y_min:.2f}",
        )

        legend_y = rect.bottom() - 8
        secondary_color = QColor(accent)
        secondary_color.setAlpha(140)
        items = [(accent, self._primary_label), (secondary_color, self._secondary_label)]
        lx = plot.left()
        for color, label in items:
            painter.setPen(QPen(color, 2))
            painter.drawLine(int(lx), int(legend_y), int(lx + 12), int(legend_y))
            painter.setPen(muted)
            painter.drawText(int(lx + 16), int(legend_y + 4), label)
            lx += 88

        if len(self._epochs) < 1:
            return

        n = max(1, len(self._epochs) - 1)

        def x_at(i: int) -> float:
            return x0 if n == 0 else x0 + (x1 - x0) * (i / n)

        def y_for(v: float) -> float:
            return y0 + (y1 - y0) * ((v - y_min) / (y_max - y_min))

        def draw_series(values: list[float], color: QColor) -> None:
            path = QPainterPath()
            started = False
            for i, value in enumerate(values):
                if value != value:
                    started = False
                    continue
                point_x, point_y = x_at(i), y_for(value)
                if not started:
                    path.moveTo(point_x, point_y)
                    started = True
                else:
                    path.lineTo(point_x, point_y)
            if started:
                painter.setPen(QPen(color, 1.8))
                painter.drawPath(path)

        draw_series(self._primary, accent)
        draw_series(self._secondary, secondary_color)


class TrainChart(QWidget):
    """Stacked loss + accuracy charts for the train stage."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("trainCharts")
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._loss = MetricChart(
            "Loss",
            primary_label="train",
            secondary_label="val",
            fallback_range=(0.0, 1.0),
            parent=self,
        )
        self._acc = MetricChart(
            "Accuracy",
            primary_label="train",
            secondary_label="val",
            fallback_range=(0.0, 1.0),
            parent=self,
        )
        layout.addWidget(self._loss, 1)
        layout.addWidget(self._acc, 1)

    def clear(self) -> None:
        self._loss.clear()
        self._acc.clear()

    def add_epoch(
        self,
        epoch: int,
        *,
        loss: float | None = None,
        accuracy: float | None = None,
        val_loss: float | None = None,
        val_accuracy: float | None = None,
    ) -> None:
        self._loss.add_point(epoch, primary=loss, secondary=val_loss)
        self._acc.add_point(epoch, primary=accuracy, secondary=val_accuracy)

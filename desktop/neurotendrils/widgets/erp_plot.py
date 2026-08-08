"""Simple ERP grand-average plot (QPainter, no matplotlib)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from neurotendrils.core.theme import Theme

_PALETTE = [
    QColor("#2f6feb"),
    QColor("#c8443c"),
    QColor("#2a9d8f"),
    QColor("#e9c46a"),
    QColor("#9b5de5"),
    QColor("#f4a261"),
]


class ErpPlot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._times: list[float] = []
        self._averages: dict[str, list[float]] = {}
        self._title = QLabel("ERP", self)
        self._title.setObjectName("sectionLabel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title)
        self._canvas = _ErpCanvas(self)
        layout.addWidget(self._canvas, 1)

    def set_erp(self, payload: dict) -> None:
        self._times = [float(t) for t in (payload.get("times") or [])]
        self._averages = {
            str(k): [float(v) for v in vals]
            for k, vals in (payload.get("averages") or {}).items()
        }
        n = int(payload.get("n_epochs") or 0)
        names = ", ".join(self._averages.keys()) or "—"
        self._title.setText(f"ERP · {n} epochs · {names}")
        self._canvas.set_data(self._times, self._averages)
        self.update()


class _ErpCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._times: list[float] = []
        self._averages: dict[str, list[float]] = {}

    def set_data(self, times: list[float], averages: dict[str, list[float]]) -> None:
        self._times = times
        self._averages = averages
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())
        if not self._times or not self._averages:
            painter.setPen(theme.muted_text_color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No ERP yet")
            return

        plot = self.rect().adjusted(40, 12, -12, -24)
        all_vals = [v for series in self._averages.values() for v in series]
        lo, hi = min(all_vals), max(all_vals)
        if hi <= lo:
            hi = lo + 1.0
        t0, t1 = self._times[0], self._times[-1]
        span = t1 - t0 if t1 > t0 else 1.0

        # Zero line
        y0 = plot.bottom() - ((0 - lo) / (hi - lo)) * plot.height()
        pen = QPen(theme.muted_text_color())
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawLine(plot.left(), int(y0), plot.right(), int(y0))

        for i, (name, series) in enumerate(self._averages.items()):
            color = _PALETTE[i % len(_PALETTE)]
            painter.setPen(QPen(color, 1.6))
            path = QPainterPath()
            n = min(len(series), len(self._times))
            for j in range(n):
                x = plot.left() + ((self._times[j] - t0) / span) * plot.width()
                y = plot.bottom() - ((series[j] - lo) / (hi - lo)) * plot.height()
                if j == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)
            painter.drawText(plot.left() + 4, plot.top() + 14 + i * 14, name)

        painter.setPen(theme.muted_text_color())
        painter.drawText(plot.left(), self.height() - 6, f"{t0:.2f}s")
        painter.drawText(plot.right() - 40, self.height() - 6, f"{t1:.2f}s")

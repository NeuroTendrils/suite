"""EEGLAB-style ERP image: trials×time heatmap + average ERP."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from neurotendrils.core.theme import Theme

def _sequential_color(t: float) -> QColor:
    """Dark blue → cyan → yellow for trial heatmaps."""
    t = max(0.0, min(1.0, float(t)))
    if t < 0.5:
        u = t * 2.0
        return QColor(int(20 + 40 * u), int(40 + 120 * u), int(100 + 100 * u))
    u = (t - 0.5) * 2.0
    return QColor(int(60 + 195 * u), int(160 + 95 * u), int(200 - 170 * u))


class ErpImage(QWidget):
    """Trials × time heatmap with grand-average waveform below."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._trials: list[list[float]] = []
        self._times: list[float] = []
        self._title = ""
        self._heatmap = QImage()
        self._average: list[float] = []
        self._label = QLabel("ERP image", self)
        self._label.setObjectName("sectionLabel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        Theme.instance().changed.connect(self.update)

    def set_data(
        self,
        trials: list[list[float]],
        times: list[float],
        *,
        title: str = "",
    ) -> None:
        self._trials = [[float(v) for v in row] for row in trials]
        self._times = [float(t) for t in times]
        self._title = str(title)
        n_trials = len(self._trials)
        n_times = len(self._times)
        label = self._title or f"ERP image · {n_trials} trials"
        self._label.setText(label)

        if not self._trials or not self._times:
            self._heatmap = QImage()
            self._average = []
            self.update()
            return

        n_cols = min(n_times, max(len(row) for row in self._trials))
        flat = [v for row in self._trials for v in row[:n_cols]]
        lo, hi = min(flat), max(flat)
        span = hi - lo if hi > lo else 1.0

        img = QImage(n_cols, n_trials, QImage.Format.Format_ARGB32)
        for row_i, row in enumerate(self._trials):
            for col_i in range(n_cols):
                v = row[col_i] if col_i < len(row) else 0.0
                t = (v - lo) / span
                img.setPixelColor(col_i, row_i, _sequential_color(t))

        self._heatmap = img
        self._average = []
        for col_i in range(n_cols):
            vals = [
                row[col_i]
                for row in self._trials
                if col_i < len(row)
            ]
            self._average.append(sum(vals) / len(vals) if vals else 0.0)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())

        if self._heatmap.isNull() or not self._trials:
            painter.setPen(theme.muted_text_color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No ERP image yet")
            return

        top = 22
        bottom_pad = 22
        erp_h = max(48, int(self.height() * 0.28))
        heat_h = self.height() - top - erp_h - bottom_pad - 8
        if heat_h < 20:
            heat_h = 20
        plot = self.rect().adjusted(40, top, -12, -(erp_h + bottom_pad + 8))

        painter.drawImage(plot, self._heatmap.scaled(plot.size()))

        # Trial axis label
        painter.setPen(theme.muted_text_color())
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.drawText(4, plot.top(), 32, plot.height(), Qt.AlignmentFlag.AlignCenter, "trials")

        # Average ERP below heatmap
        erp_rect = self.rect().adjusted(40, plot.bottom() + 8, -12, -bottom_pad)
        if self._average and self._times:
            lo, hi = min(self._average), max(self._average)
            if hi <= lo:
                hi = lo + 1.0
            t0, t1 = self._times[0], self._times[-1]
            tspan = t1 - t0 if t1 > t0 else 1.0
            n = min(len(self._average), len(self._times))

            pen = QPen(theme.muted_text_color())
            pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen)
            y0 = erp_rect.bottom() - ((0 - lo) / (hi - lo)) * erp_rect.height()
            if lo <= 0 <= hi:
                painter.drawLine(erp_rect.left(), int(y0), erp_rect.right(), int(y0))

            path = QPainterPath()
            for j in range(n):
                x = erp_rect.left() + ((self._times[j] - t0) / tspan) * erp_rect.width()
                y = erp_rect.bottom() - ((self._average[j] - lo) / (hi - lo)) * erp_rect.height()
                if j == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.setPen(QPen(theme.accent_color(), 1.8))
            painter.drawPath(path)
            painter.setPen(theme.muted_text_color())
            painter.drawText(erp_rect.left(), self.height() - 6, f"{t0:.2f}s")
            painter.drawText(erp_rect.right() - 40, self.height() - 6, f"{t1:.2f}s")
            painter.drawText(erp_rect.left() - 36, erp_rect.top() + 10, "μV")

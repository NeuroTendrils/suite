"""Multi-channel PSD line plot (QPainter, no matplotlib)."""

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
    QColor("#577590"),
    QColor("#f72585"),
]


class SpectraPlot(QWidget):
    """Frequency × power (dB) line plot for multiple channels."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(180)
        self._freqs: list[float] = []
        self._channels: dict[str, list[float]] = {}
        self._title = QLabel("Spectra", self)
        self._title.setObjectName("sectionLabel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._title)
        self._canvas = _SpectraCanvas(self)
        layout.addWidget(self._canvas, 1)
        Theme.instance().changed.connect(self.update)

    def set_spectra(self, freqs: list[float], channels: dict[str, list[float]]) -> None:
        self._freqs = [float(f) for f in freqs]
        self._channels = {
            str(k): [float(v) for v in vals] for k, vals in channels.items()
        }
        names = ", ".join(list(self._channels.keys())[:4])
        extra = len(self._channels) - 4
        if extra > 0:
            names += f" +{extra}"
        self._title.setText(f"Spectra · {names or '—'}")
        self._canvas.set_data(self._freqs, self._channels)
        self.update()


class _SpectraCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(140)
        self._freqs: list[float] = []
        self._channels: dict[str, list[float]] = {}

    def set_data(self, freqs: list[float], channels: dict[str, list[float]]) -> None:
        self._freqs = freqs
        self._channels = channels
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())

        if not self._freqs or not self._channels:
            painter.setPen(theme.muted_text_color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No spectra yet")
            return

        plot = self.rect().adjusted(44, 8, -12, -28)
        all_vals = [v for series in self._channels.values() for v in series]
        lo, hi = min(all_vals), max(all_vals)
        if hi <= lo:
            hi = lo + 1.0
        f0, f1 = self._freqs[0], self._freqs[-1]
        fspan = f1 - f0 if f1 > f0 else 1.0

        painter.setPen(theme.muted_text_color())
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.drawText(plot.left(), self.height() - 8, f"{f0:.0f} Hz")
        painter.drawText(plot.right() - 36, self.height() - 8, f"{f1:.0f} Hz")
        painter.drawText(4, plot.top() + 10, f"{hi:.0f} dB")
        painter.drawText(4, plot.bottom() - 4, f"{lo:.0f} dB")

        for i, (name, series) in enumerate(self._channels.items()):
            color = _PALETTE[i % len(_PALETTE)]
            painter.setPen(QPen(color, 1.4))
            path = QPainterPath()
            n = min(len(series), len(self._freqs))
            for j in range(n):
                x = plot.left() + ((self._freqs[j] - f0) / fspan) * plot.width()
                y = plot.bottom() - ((series[j] - lo) / (hi - lo)) * plot.height()
                if j == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)

        # Truncated legend
        legend_x = plot.left() + 4
        legend_y = plot.top() + 4
        max_items = max(1, plot.width() // 72)
        items = list(self._channels.items())[:max_items]
        for i, (name, _) in enumerate(items):
            color = _PALETTE[i % len(_PALETTE)]
            y = legend_y + i * 13
            painter.setPen(QPen(color, 2))
            painter.drawLine(int(legend_x), int(y), int(legend_x + 10), int(y))
            label = name if len(name) <= 10 else name[:9] + "…"
            painter.setPen(theme.muted_text_color())
            painter.drawText(int(legend_x + 14), int(y + 4), label)
        if len(self._channels) > max_items:
            painter.drawText(
                int(legend_x),
                int(legend_y + max_items * 13 + 2),
                f"+{len(self._channels) - max_items} more",
            )

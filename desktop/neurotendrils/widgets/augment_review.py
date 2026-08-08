"""Before/after augment trial review (accept / reject suggestions)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme


class AugmentReview(QWidget):
    """Step through suggested augment pairs; track accepts."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pairs: list[dict] = []
        self._times: list[float] = []
        self._index = 0
        self._accepted: set[int] = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self._status = QLabel("No augment suggestions", self)
        self._status.setObjectName("mutedLabel")
        root.addWidget(self._status)

        self._canvas = _PairCanvas(self)
        root.addWidget(self._canvas, 1)

        row = QHBoxLayout()
        prev = QPushButton("Previous", self)
        prev.setObjectName("ghostButton")
        prev.clicked.connect(self._prev)
        row.addWidget(prev)
        self._accept_btn = QPushButton("Accept", self)
        self._accept_btn.setObjectName("primaryButton")
        self._accept_btn.clicked.connect(self._accept)
        row.addWidget(self._accept_btn)
        reject = QPushButton("Skip", self)
        reject.setObjectName("ghostButton")
        reject.clicked.connect(self._next)
        row.addWidget(reject)
        nxt = QPushButton("Next", self)
        nxt.setObjectName("ghostButton")
        nxt.clicked.connect(self._next)
        row.addWidget(nxt)
        root.addLayout(row)

    def set_preview(self, payload: dict) -> None:
        self._pairs = list(payload.get("pairs") or [])
        self._times = [float(t) for t in (payload.get("times") or [])]
        self._index = 0
        self._accepted.clear()
        self._render()

    def accepted_indices(self) -> list[int]:
        return sorted(self._accepted)

    def _render(self) -> None:
        if not self._pairs:
            self._status.setText("No augment suggestions")
            self._canvas.clear()
            return
        pair = self._pairs[self._index]
        accepted = "accepted" if pair["index"] in self._accepted else "pending"
        self._status.setText(
            f"Pair {self._index + 1}/{len(self._pairs)} · class={pair.get('class')} · {accepted}"
        )
        self._canvas.set_pair(self._times, pair.get("before") or [], pair.get("after") or [])
        self.changed.emit()

    def _prev(self) -> None:
        if not self._pairs:
            return
        self._index = (self._index - 1) % len(self._pairs)
        self._render()

    def _next(self) -> None:
        if not self._pairs:
            return
        self._index = (self._index + 1) % len(self._pairs)
        self._render()

    def _accept(self) -> None:
        if not self._pairs:
            return
        self._accepted.add(int(self._pairs[self._index]["index"]))
        self._next()


class _PairCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(160)
        self._times: list[float] = []
        self._before: list[float] = []
        self._after: list[float] = []

    def clear(self) -> None:
        self._times, self._before, self._after = [], [], []
        self.update()

    def set_pair(self, times: list[float], before: list[float], after: list[float]) -> None:
        self._times = times
        self._before = before
        self._after = after
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())
        if not self._times or not self._before:
            painter.setPen(theme.muted_text_color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "—")
            return
        plot = self.rect().adjusted(12, 12, -12, -12)
        vals = self._before + self._after
        lo, hi = min(vals), max(vals)
        if hi <= lo:
            hi = lo + 1.0
        t0, t1 = self._times[0], self._times[-1]
        span = t1 - t0 if t1 > t0 else 1.0

        def draw_series(series: list[float], color: QColor) -> None:
            painter.setPen(QPen(color, 1.5))
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

        draw_series(self._before, theme.muted_text_color())
        draw_series(self._after, theme.accent_color())
        painter.setPen(theme.muted_text_color())
        painter.drawText(plot.left(), plot.top() + 12, "before (muted) / after (accent)")

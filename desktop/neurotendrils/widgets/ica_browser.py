"""ICA component contribution browser (manual exclude decisions)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme


class _Sparkline(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setMinimumWidth(120)
        self._samples: list[float] = []

    def set_samples(self, samples: list[float]) -> None:
        self._samples = [float(v) for v in samples]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())
        if len(self._samples) < 2:
            return
        lo = min(self._samples)
        hi = max(self._samples)
        if hi <= lo:
            hi = lo + 1.0
        path = QPainterPath()
        w = max(1, self.width() - 2)
        h = max(1, self.height() - 4)
        for i, v in enumerate(self._samples):
            x = 1 + (i / (len(self._samples) - 1)) * w
            y = 2 + (1.0 - (v - lo) / (hi - lo)) * h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(theme.accent_color(), 1.2))
        painter.drawPath(path)


class _ContribBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(10)
        self.setMinimumWidth(80)
        self._frac = 0.0

    def set_fraction(self, frac: float) -> None:
        self._frac = max(0.0, min(1.0, float(frac)))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())
        fill = QColor(theme.accent_color())
        w = int(self.width() * self._frac)
        painter.fillRect(0, 0, w, self.height(), fill)


class IcaBrowser(QWidget):
    """List ICA components with contribution bars, sparklines, and exclude toggles."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self._hint = QLabel(
            "Review ICA components. Suggested EOG-like components start excluded. "
            "Check a component to exclude it from the cleaned data on the next run "
            "(set Exclude indices in the ICA plan step, or re-run after editing).",
            self,
        )
        self._hint.setObjectName("mutedLabel")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        self._list = QVBoxLayout(body)
        self._list.setContentsMargins(0, 0, 0, 0)
        self._list.setSpacing(6)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self._checks: list[QCheckBox] = []
        self._n = 0

    def set_summary(self, summary: dict) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._checks.clear()
        contrib = summary.get("contributions") or []
        waveforms = summary.get("waveforms") or []
        suggested = set(int(i) for i in (summary.get("suggested_exclude") or []))
        self._n = int(summary.get("n_components") or len(contrib))
        for i in range(self._n):
            frac = float(contrib[i]) if i < len(contrib) else 0.0
            row = QWidget(self)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            check = QCheckBox(f"IC{i:02d}", row)
            check.setChecked(i in suggested)
            check.toggled.connect(lambda *_: self.changed.emit())
            layout.addWidget(check)
            bar = _ContribBar(row)
            bar.set_fraction(frac)
            layout.addWidget(bar, 1)
            pct = QLabel(f"{frac * 100:.1f}%", row)
            pct.setObjectName("mutedLabel")
            pct.setFixedWidth(48)
            layout.addWidget(pct)
            spark = _Sparkline(row)
            if i < len(waveforms):
                spark.set_samples(list(waveforms[i] or []))
            layout.addWidget(spark, 2)
            self._list.addWidget(row)
            self._checks.append(check)
        self._list.addStretch(1)
        self.changed.emit()

    def exclude_indices(self) -> list[int]:
        return [i for i, check in enumerate(self._checks) if check.isChecked()]

    def exclude_csv(self) -> str:
        return ",".join(str(i) for i in self.exclude_indices())

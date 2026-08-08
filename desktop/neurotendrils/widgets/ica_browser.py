"""ICA component contribution browser (manual exclude decisions)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class IcaBrowser(QWidget):
    """List ICA components with contribution fractions and exclude toggles."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        self._hint = QLabel(
            "Review ICA components. Suggested EOG-like components start excluded.",
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
        self._list.setSpacing(4)
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
        suggested = set(int(i) for i in (summary.get("suggested_exclude") or []))
        self._n = int(summary.get("n_components") or len(contrib))
        for i in range(self._n):
            frac = float(contrib[i]) if i < len(contrib) else 0.0
            row = QWidget(self)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            check = QCheckBox(f"IC{i:02d}", row)
            check.setChecked(i in suggested)
            check.toggled.connect(lambda *_: self.changed.emit())
            layout.addWidget(check)
            bar = QLabel(f"{frac * 100:.1f}% contribution", row)
            bar.setObjectName("mutedLabel")
            layout.addWidget(bar, 1)
            self._list.addWidget(row)
            self._checks.append(check)
        self._list.addStretch(1)
        self.changed.emit()

    def exclude_indices(self) -> list[int]:
        return [i for i, check in enumerate(self._checks) if check.isChecked()]

    def exclude_csv(self) -> str:
        return ",".join(str(i) for i in self.exclude_indices())

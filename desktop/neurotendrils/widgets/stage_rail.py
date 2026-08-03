"""Horizontal stage rail: numbered steps, completion state, animated underline."""

from __future__ import annotations

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from neurotendrils.widgets.motion import DURATION_FAST

_INDICATOR_HEIGHT = 2
_CONNECTOR_WIDTH = 28


class _StageChip(QWidget):
    activated = Signal()

    def __init__(self, number: int, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stageChip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(8)

        self._index = QLabel(str(number), self)
        self._index.setObjectName("stageIndex")
        self._index.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._index.setFixedSize(18, 18)
        self._index.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._label = QLabel(label, self)
        self._label.setObjectName("stageLabel")
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout.addWidget(self._index)
        layout.addWidget(self._label)

        self._unlocked = True
        self.set_state(current=False, complete=False, unlocked=True)

    def set_state(self, *, current: bool, complete: bool, unlocked: bool) -> None:
        self._unlocked = unlocked
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if unlocked
            else Qt.CursorShape.ForbiddenCursor
        )
        if complete:
            index_name = "stageIndexDone"
        elif current:
            index_name = "stageIndexCurrent"
        elif unlocked:
            index_name = "stageIndex"
        else:
            index_name = "stageIndexLocked"

        if current:
            label_name = "stageLabelCurrent"
        elif unlocked:
            label_name = "stageLabel"
        else:
            label_name = "stageLabelLocked"

        for widget, name in ((self._index, index_name), (self._label, label_name)):
            if widget.objectName() != name:
                widget.setObjectName(name)
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._unlocked:
            self.activated.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class StageRail(QWidget):
    """Click-to-jump stage header; locked stages ignore clicks."""

    stageActivated = Signal(int)

    def __init__(self, labels: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stageRail")
        self._current = 0
        self._chips: list[_StageChip] = []
        self._connectors: list[QFrame] = []
        self._complete: list[bool] = [False] * len(labels)
        self._unlocked: list[bool] = [i == 0 for i in range(len(labels))]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._row = QWidget(self)
        row_layout = QHBoxLayout(self._row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)
        for position, label in enumerate(labels):
            if position:
                connector = QFrame(self._row)
                connector.setObjectName("stageConnector")
                connector.setFrameShape(QFrame.Shape.NoFrame)
                connector.setFixedSize(_CONNECTOR_WIDTH, 1)
                row_layout.addWidget(connector, 0, Qt.AlignmentFlag.AlignVCenter)
                self._connectors.append(connector)
            chip = _StageChip(position + 1, label, self._row)
            chip.activated.connect(lambda i=position: self.stageActivated.emit(i))
            row_layout.addWidget(chip)
            self._chips.append(chip)
        row_layout.addStretch(1)

        self._track = QWidget(self)
        self._track.setFixedHeight(_INDICATOR_HEIGHT)
        self._indicator = QFrame(self._track)
        self._indicator.setObjectName("stageIndicator")
        self._indicator.setFixedHeight(_INDICATOR_HEIGHT)

        self._baseline = QFrame(self)
        self._baseline.setObjectName("separator")
        self._baseline.setFixedHeight(1)

        root.addWidget(self._row)
        root.addWidget(self._track)
        root.addWidget(self._baseline)

        self._sync()

    def current_index(self) -> int:
        return self._current

    def set_current(self, index: int) -> None:
        if index < 0 or index >= len(self._chips):
            return
        changed = index != self._current
        self._current = index
        self._sync()
        self._move_indicator(animate=changed)

    def set_complete(self, index: int, complete: bool) -> None:
        if 0 <= index < len(self._complete) and self._complete[index] != complete:
            self._complete[index] = complete
            self._sync()

    def set_unlocked(self, index: int, unlocked: bool) -> None:
        if 0 <= index < len(self._unlocked) and self._unlocked[index] != unlocked:
            self._unlocked[index] = unlocked
            self._sync()

    def is_unlocked(self, index: int) -> bool:
        return 0 <= index < len(self._unlocked) and self._unlocked[index]

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._move_indicator(animate=False)

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._move_indicator(animate=False)

    def _sync(self) -> None:
        for position, chip in enumerate(self._chips):
            chip.set_state(
                current=position == self._current,
                complete=self._complete[position],
                unlocked=self._unlocked[position] or position == self._current,
            )
        for position, connector in enumerate(self._connectors):
            name = "stageConnectorDone" if self._complete[position] else "stageConnector"
            if connector.objectName() != name:
                connector.setObjectName(name)
                connector.style().unpolish(connector)
                connector.style().polish(connector)

    def _move_indicator(self, *, animate: bool) -> None:
        if not self._chips:
            return
        chip = self._chips[self._current]
        target = QRect(chip.x(), 0, chip.width(), _INDICATOR_HEIGHT)
        if not animate or not self._indicator.isVisible():
            self._indicator.setGeometry(target)
            return
        existing = self._indicator.property("_ntSlide")
        if isinstance(existing, QPropertyAnimation):
            existing.stop()
        anim = QPropertyAnimation(self._indicator, QByteArray(b"geometry"), self)
        anim.setDuration(DURATION_FAST)
        anim.setStartValue(self._indicator.geometry())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._indicator.setProperty("_ntSlide", anim)
        anim.start()

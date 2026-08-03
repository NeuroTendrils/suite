"""Staged workspace shell: rail on top, one stage at a time, contextual footer.

Replaces the long vertical form with a flow the user moves through, so state
stays visible in the context strip while the body only shows the current step.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.widgets.layoututil import clear_layout
from neurotendrils.widgets.motion import slide_stack, stagger_in
from neurotendrils.widgets.rows import hairline
from neurotendrils.widgets.section import eyebrow_font
from neurotendrils.widgets.stage_rail import StageRail

MAX_STAGE_WIDTH = 0  # 0 = fill the viewport


@dataclass
class _Stage:
    key: str
    label: str
    widget: QWidget
    primary: str


class ContextStrip(QWidget):
    """Compact key/value summary of everything gathered so far."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("contextStrip")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(24)
        self._items: list[tuple[str, str]] = []
        self.hide()

    def set_items(self, items: list[tuple[str, str]]) -> None:
        if items == self._items:
            return
        self._items = items
        clear_layout(self._layout)
        if not items:
            self.hide()
            return

        cells: list[QWidget] = []
        for position, (key, value) in enumerate(items):
            if position:
                divider = QFrame(self)
                divider.setObjectName("statDivider")
                divider.setFrameShape(QFrame.Shape.NoFrame)
                divider.setFixedWidth(1)
                self._layout.addWidget(divider)
            cell = self._cell(key, value)
            self._layout.addWidget(cell)
            cells.append(cell)
        self._layout.addStretch(1)
        self.show()
        stagger_in(cells, gap=35)

    def _cell(self, key: str, value: str) -> QWidget:
        cell = QWidget(self)
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        key_label = QLabel(key.upper(), cell)
        key_label.setObjectName("contextKey")
        key_label.setFont(eyebrow_font(key_label.font()))
        value_label = QLabel(value, cell)
        value_label.setObjectName("contextValue")
        value_label.setToolTip(value)
        metrics = value_label.fontMetrics()
        value_label.setMaximumWidth(160)
        value_label.setText(metrics.elidedText(value, Qt.TextElideMode.ElideMiddle, 160))
        layout.addWidget(key_label)
        layout.addWidget(value_label)
        return cell


class StageFlow(QWidget):
    """Container for a sequence of stages with animated transitions."""

    stageChanged = Signal(str)
    primaryTriggered = Signal(str)

    def __init__(
        self, title: str, description: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._stages: list[_Stage] = []
        self._index_of: dict[str, int] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget(self)
        self._header_layout = QVBoxLayout(header)
        self._header_layout.setContentsMargins(32, 28, 32, 0)
        self._header_layout.setSpacing(8)

        title_label = QLabel(title, header)
        title_label.setObjectName("pageTitle")
        description_label = QLabel(description, header)
        description_label.setObjectName("pageDescription")
        description_label.setWordWrap(True)
        description_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        # Keep the blurb from colliding with the rail / stage body.
        description_label.setMinimumHeight(
            description_label.fontMetrics().lineSpacing() * 2
        )
        self._header_layout.addWidget(title_label)
        self._header_layout.addWidget(description_label)
        self._header_layout.addSpacing(16)

        self.context = ContextStrip(header)
        self._header_layout.addWidget(self.context)
        self._header_layout.addSpacing(20)
        root.addWidget(header)

        self._rail: QWidget | None = None
        self._rail_slot = QWidget(self)
        rail_slot_layout = QVBoxLayout(self._rail_slot)
        rail_slot_layout.setContentsMargins(32, 0, 32, 0)
        rail_slot_layout.setSpacing(0)
        self._rail_slot_layout = rail_slot_layout
        root.addWidget(self._rail_slot)

        self._body = QStackedWidget(self)
        self._body.setObjectName("pageStack")
        root.addWidget(self._body, 1)

        root.addWidget(hairline(self))
        footer = QWidget(self)
        footer.setObjectName("stageFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(32, 12, 32, 14)
        footer_layout.setSpacing(8)

        self._status = QLabel("", footer)
        self._status.setObjectName("stageStatus")
        self._status.setWordWrap(False)

        self._back = QPushButton("Back", footer)
        self._back.setObjectName("secondaryButton")
        self._back.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._back.clicked.connect(self.retreat)

        self._primary = QPushButton("Continue", footer)
        self._primary.setObjectName("primaryButton")
        self._primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self._primary.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._primary.clicked.connect(
            lambda: self.primaryTriggered.emit(self.current_key())
        )

        footer_layout.addWidget(self._status, 1)
        footer_layout.addWidget(self._back)
        footer_layout.addWidget(self._primary)
        root.addWidget(footer)

    # ---------- construction ----------

    def add_stage(
        self, key: str, label: str, widget: QWidget, *, primary: str = "Continue"
    ) -> None:
        scroll = QScrollArea(self._body)
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        viewport = QWidget(scroll)
        viewport.setObjectName("pageContent")
        viewport_layout = QHBoxLayout(viewport)
        viewport_layout.setContentsMargins(32, 20, 32, 28)
        viewport_layout.setSpacing(0)

        # A filling column keeps word-wrapped rows at their true height; top
        # alignment would size the stage from its width-agnostic size hint.
        column = QWidget(viewport)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        if MAX_STAGE_WIDTH > 0:
            widget.setMaximumWidth(MAX_STAGE_WIDTH)
        column_layout.addWidget(widget)
        column_layout.addStretch(1)
        viewport_layout.addWidget(column, 1)
        scroll.setWidget(viewport)

        self._index_of[key] = len(self._stages)
        self._stages.append(_Stage(key, label, widget, primary))
        self._body.addWidget(scroll)

    def finalize(self) -> None:
        """Build the rail once every stage is registered."""
        rail = StageRail([stage.label for stage in self._stages], self._rail_slot)
        rail.stageActivated.connect(self._on_rail_activated)
        self._rail_slot_layout.addWidget(rail)
        self._rail = rail
        if self._stages:
            self._body.setCurrentIndex(0)
            self._sync_footer()

    # ---------- state ----------

    def current_index(self) -> int:
        return self._body.currentIndex()

    def current_key(self) -> str:
        index = self._body.currentIndex()
        if 0 <= index < len(self._stages):
            return self._stages[index].key
        return ""

    def stage_keys(self) -> list[str]:
        return [stage.key for stage in self._stages]

    def go_to(self, key: str, *, animate: bool = True) -> None:
        index = self._index_of.get(key)
        if index is None or index == self._body.currentIndex():
            return
        forward = index > self._body.currentIndex()
        if animate:
            slide_stack(self._body, index, forward=forward)
        else:
            self._body.setCurrentIndex(index)
        if self._rail is not None:
            self._rail.set_current(index)
        self._sync_footer()
        self.stageChanged.emit(self._stages[index].key)

    def advance(self) -> None:
        index = self._body.currentIndex()
        if index + 1 < len(self._stages):
            self.go_to(self._stages[index + 1].key)

    def retreat(self) -> None:
        index = self._body.currentIndex()
        if index > 0:
            self.go_to(self._stages[index - 1].key)

    def set_complete(self, key: str, complete: bool) -> None:
        index = self._index_of.get(key)
        if index is not None and self._rail is not None:
            self._rail.set_complete(index, complete)

    def set_unlocked(self, key: str, unlocked: bool) -> None:
        index = self._index_of.get(key)
        if index is not None and self._rail is not None:
            self._rail.set_unlocked(index, unlocked)

    def set_status(self, text: str) -> None:
        self._status.setToolTip(text)
        # Keep the footer from shoving Back/Continue off-screen on long status.
        metrics = self._status.fontMetrics()
        width = max(120, self._status.width() or 280)
        self._status.setText(
            metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)
        )

    def set_primary(
        self, label: str = "", *, enabled: bool = True, visible: bool = True
    ) -> None:
        if label:
            self._primary.setText(label)
        self._primary.setEnabled(enabled)
        self._primary.setVisible(visible)

    def set_context(self, items: list[tuple[str, str]]) -> None:
        self.context.set_items(items)

    # ---------- internals ----------

    def _on_rail_activated(self, index: int) -> None:
        if 0 <= index < len(self._stages):
            self.go_to(self._stages[index].key)

    def _sync_footer(self) -> None:
        index = self._body.currentIndex()
        self._back.setVisible(index > 0)
        if 0 <= index < len(self._stages):
            self._primary.setText(self._stages[index].primary)

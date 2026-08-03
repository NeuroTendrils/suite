"""Full-window in-app modal overlay (scrim + centered panel)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget


@dataclass
class _Layer:
    widget: QWidget
    own: bool
    dismissible: bool
    max_width: int
    max_height: int


class ModalHost(QWidget):
    """Covers ``appRoot``; present panels instead of spawning OS windows."""

    dismissed = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("modalHost")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

        self._layers: list[_Layer] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        self._panel = QFrame(self)
        self._panel.setObjectName("modalPanel")
        self._panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._panel.setMaximumWidth(820)
        self._panel.setMaximumHeight(640)
        self._body = QVBoxLayout(self._panel)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(0)
        row.addWidget(self._panel, 0)
        row.addStretch(1)

        root.addLayout(row)
        root.addStretch(1)

        parent.installEventFilter(self)
        self._sync_geometry()

    def is_open(self) -> bool:
        return self.isVisible() and bool(self._layers)

    def present(
        self,
        widget: QWidget,
        *,
        dismissible: bool = True,
        own: bool = True,
        max_width: int = 720,
        max_height: int = 560,
    ) -> None:
        if self._layers:
            current = self._layers[-1].widget
            self._body.removeWidget(current)
            current.hide()
            current.setParent(self)

        layer = _Layer(widget, own, dismissible, max_width, max_height)
        self._layers.append(layer)
        self._show_layer(layer)

    def dismiss(self, *, animate: bool = True) -> None:
        del animate  # reserved; avoid translucent whole-tree fades
        if not self._layers:
            self.hide()
            return

        layer = self._layers.pop()
        self._body.removeWidget(layer.widget)
        layer.widget.setParent(None)
        if layer.own:
            layer.widget.deleteLater()

        if self._layers:
            self._show_layer(self._layers[-1])
            self.dismissed.emit()
            return

        self.hide()
        self.dismissed.emit()

    def _show_layer(self, layer: _Layer) -> None:
        self._panel.setMaximumWidth(layer.max_width)
        self._panel.setMaximumHeight(layer.max_height)
        # Size panel to content instead of stretching empty transparent area.
        self._panel.setMinimumWidth(min(380, layer.max_width))
        layer.widget.setParent(self._panel)
        layer.widget.show()
        self._body.addWidget(layer.widget)
        self._sync_geometry()
        self.show()
        self.raise_()
        # Clear any leftover opacity effect from earlier builds.
        self.setGraphicsEffect(None)
        layer.widget.setFocus(Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self.parent() and event.type() == QEvent.Type.Resize:
            self._sync_geometry()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._layers:
            return super().mousePressEvent(event)
        if (
            self._layers[-1].dismissible
            and event.button() == Qt.MouseButton.LeftButton
            and not self._panel.geometry().contains(event.position().toPoint())
        ):
            self.dismiss()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            self._layers
            and self._layers[-1].dismissible
            and event.key() == Qt.Key.Key_Escape
        ):
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(0, 0, parent.width(), parent.height())

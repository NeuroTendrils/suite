"""Small Qt layout helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QLayout


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is None:
            child = item.layout()
            if child is not None:
                clear_layout(child)
            continue
        # Detach before deleteLater: a widget awaiting deletion stays visible and
        # would paint over whatever replaces it.
        widget.setGraphicsEffect(None)
        widget.setParent(None)
        widget.deleteLater()

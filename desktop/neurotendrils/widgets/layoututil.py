"""Small Qt layout helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QLayout


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()

"""Map tabular columns (TXT/CSV) to EEG channels / marker / time."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ColumnMap:
    marker_col: int | None = None
    time_col: int | None = None
    skip_cols: list[int] | None = None
    # Remaining numeric columns are treated as channels in order.


class ColumnMapPanel(QWidget):
    """Lightweight column-role picker for lab TXT imports."""

    def __init__(
        self,
        headers: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._headers = list(headers)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        root.addWidget(
            QLabel("Map columns for this tabular recording.", self)
        )

        form = QFormLayout()
        self._marker = QComboBox(self)
        self._time = QComboBox(self)
        options = ["(none)"] + [
            f"{i}: {name}" for i, name in enumerate(self._headers)
        ]
        self._marker.addItems(options)
        self._time.addItems(options)
        # Heuristic defaults
        for i, name in enumerate(self._headers):
            lower = name.lower()
            if self._marker.currentIndex() == 0 and any(
                tok in lower for tok in ("marker", "event", "label", "stim", "code")
            ):
                self._marker.setCurrentIndex(i + 1)
            if self._time.currentIndex() == 0 and any(
                tok in lower for tok in ("time", "t", "timestamp", "sec")
            ):
                self._time.setCurrentIndex(i + 1)
        form.addRow("Marker column", self._marker)
        form.addRow("Time column", self._time)
        root.addLayout(form)

    def column_map(self) -> ColumnMap:
        marker = self._marker.currentIndex() - 1
        time_col = self._time.currentIndex() - 1
        return ColumnMap(
            marker_col=marker if marker >= 0 else None,
            time_col=time_col if time_col >= 0 else None,
        )


def present_column_map(
    anchor: QWidget,
    headers: list[str],
) -> ColumnMap | None:
    """Show column map in the modal host; return map or None if cancelled."""
    from neurotendrils.widgets import modals

    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(20, 18, 20, 16)
    layout.setSpacing(12)
    title = QLabel("Column map", panel)
    title.setObjectName("inspectorTitle")
    layout.addWidget(title)
    mapper = ColumnMapPanel(headers, panel)
    layout.addWidget(mapper, 1)

    result: dict[str, ColumnMap | None] = {"value": None}
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        panel,
    )

    def _accept() -> None:
        result["value"] = mapper.column_map()
        host = modals.find_host(anchor)
        if host is not None:
            host.dismiss()

    def _reject() -> None:
        result["value"] = None
        host = modals.find_host(anchor)
        if host is not None:
            host.dismiss()

    buttons.accepted.connect(_accept)
    buttons.rejected.connect(_reject)
    layout.addWidget(buttons, 0, Qt.AlignmentFlag.AlignRight)

    host = modals.present(anchor, panel, max_width=480, max_height=360)
    if host is None:
        return mapper.column_map()
    modals._run_until(host)  # noqa: SLF001 — same pattern as other modal helpers
    return result["value"]

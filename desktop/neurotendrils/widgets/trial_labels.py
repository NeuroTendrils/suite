"""Event code → class name mapping editor (manual prep)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class TrialLabelEditor(QWidget):
    """Editable table of annotation/event codes mapped to class labels."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("trialLabelEditor")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(QLabel("Event → class map", self), 1)
        add = QPushButton("Add row", self)
        add.setObjectName("ghostButton")
        add.setCursor(self.cursor())
        add.clicked.connect(self._add_row)
        header.addWidget(add)
        root.addLayout(header)

        self._table = QTableWidget(0, 2, self)
        self._table.setHorizontalHeaderLabels(["Event / code", "Class name"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.itemChanged.connect(lambda *_: self.changed.emit())
        root.addWidget(self._table, 1)

    def set_mapping(self, mapping: dict[str, str]) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for code, label in mapping.items():
            self._append(str(code), str(label))
        self._table.blockSignals(False)
        self.changed.emit()

    def set_codes(self, codes: list[str], mapping: dict[str, str] | None = None) -> None:
        mapping = mapping or {}
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for code in codes:
            self._append(str(code), str(mapping.get(code, mapping.get(code.lower(), code))))
        self._table.blockSignals(False)
        self.changed.emit()

    def mapping(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in range(self._table.rowCount()):
            code_item = self._table.item(row, 0)
            class_item = self._table.item(row, 1)
            code = (code_item.text() if code_item else "").strip()
            label = (class_item.text() if class_item else "").strip()
            if code and label:
                out[code] = label
        return out

    def class_names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for label in self.mapping().values():
            if label not in seen:
                seen.add(label)
                names.append(label)
        return names

    def _add_row(self) -> None:
        self._append("", "")

    def _append(self, code: str, label: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(code))
        self._table.setItem(row, 1, QTableWidgetItem(label))


class AboutEditor(QWidget):
    """Optional dataset about / tags / notes."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        root.addWidget(QLabel("About", self))
        self._summary = QLineEdit(self)
        self._summary.setPlaceholderText("Short summary (optional)")
        self._summary.textChanged.connect(lambda *_: self.changed.emit())
        root.addWidget(self._summary)

        self._tags = QLineEdit(self)
        self._tags.setPlaceholderText("Tags, comma-separated")
        self._tags.textChanged.connect(lambda *_: self.changed.emit())
        root.addWidget(self._tags)

        self._notes = QLineEdit(self)
        self._notes.setPlaceholderText("Notes")
        self._notes.textChanged.connect(lambda *_: self.changed.emit())
        root.addWidget(self._notes)

    def set_about(self, summary: str = "", tags: list[str] | None = None, notes: str = "") -> None:
        self._summary.setText(summary or "")
        self._tags.setText(", ".join(tags or []))
        self._notes.setText(notes or "")

    def about_dict(self) -> dict[str, object]:
        tags = [t.strip() for t in self._tags.text().split(",") if t.strip()]
        return {
            "summary": self._summary.text().strip(),
            "tags": tags,
            "notes": self._notes.text().strip(),
        }

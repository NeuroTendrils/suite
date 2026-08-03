"""Reusable schema-driven parameter form (shared by Flow and Studio)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


def build_editors(
    schemas: list[dict[str, Any]],
    values: dict[str, Any],
    parent: QWidget,
    *,
    decimals: int = 3,
    single_step: float = 0.1,
) -> dict[str, QWidget]:
    editors: dict[str, QWidget] = {}
    for schema in schemas:
        key = schema["id"]
        ptype = schema["type"]
        current = values.get(key, schema.get("default"))
        editor: QWidget
        if ptype == "boolean":
            editor = QCheckBox(parent)
            editor.setChecked(bool(current))
        elif ptype == "enum":
            editor = QComboBox(parent)
            for option in schema.get("enum", []):
                editor.addItem(str(option))
            idx = editor.findText(str(current))
            editor.setCurrentIndex(max(0, idx))
        elif ptype == "string":
            editor = QLineEdit(parent)
            editor.setText("" if current is None else str(current))
        else:
            editor = QDoubleSpinBox(parent)
            editor.setDecimals(0 if ptype == "integer" else decimals)
            editor.setSingleStep(1.0 if ptype == "integer" else single_step)
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            editor.setMinimum(float(minimum) if minimum is not None else -1e12)
            editor.setMaximum(float(maximum) if maximum is not None else 1e12)
            if schema.get("unit"):
                editor.setSuffix(f" {schema['unit']}")
            editor.setValue(float(current if current is not None else 0))
        if schema.get("help"):
            editor.setToolTip(str(schema["help"]))
        editors[key] = editor
    return editors


def collect_values(
    schemas: list[dict[str, Any]], editors: dict[str, QWidget]
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for schema in schemas:
        key = schema["id"]
        editor = editors[key]
        ptype = schema["type"]
        if isinstance(editor, QCheckBox):
            values[key] = editor.isChecked()
        elif isinstance(editor, QComboBox):
            values[key] = editor.currentText()
        elif isinstance(editor, QLineEdit):
            values[key] = editor.text()
        elif isinstance(editor, QDoubleSpinBox):
            if ptype == "integer":
                values[key] = int(round(editor.value()))
            else:
                values[key] = float(editor.value())
    return values


class SchemaEditDialog(QDialog):
    """Modal editor for a list of param schemas."""

    def __init__(
        self,
        title: str,
        intro: str,
        schemas: list[dict[str, Any]],
        values: dict[str, Any],
        validator,
        parent: QWidget | None = None,
        *,
        decimals: int = 3,
        single_step: float = 0.1,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._schemas = schemas
        self._validator = validator
        self._values = dict(values)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(intro, self))

        form_host = QWidget(self)
        form = QFormLayout(form_host)
        self._editors = build_editors(
            schemas, values, form_host, decimals=decimals, single_step=single_step
        )
        for schema in schemas:
            form.addRow(schema.get("label", schema["id"]), self._editors[schema["id"]])
        layout.addWidget(form_host)

        self._error = QLabel("", self)
        self._error.setObjectName("stepEditError")
        self._error.hide()
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        values = collect_values(self._schemas, self._editors)
        err = self._validator(values)
        if err:
            self._error.setText(err)
            self._error.show()
            return
        self._values = values
        self.accept()

    def values(self) -> dict[str, Any]:
        return dict(self._values)


class SchemaFormWidget(QWidget):
    """Inline form that emits values_changed on every edit."""

    values_changed = Signal(dict)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        decimals: int = 6,
        single_step: float = 0.0001,
    ) -> None:
        super().__init__(parent)
        self._schemas: list[dict[str, Any]] = []
        self._editors: dict[str, QWidget] = {}
        self._decimals = decimals
        self._single_step = single_step
        self._layout = QFormLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def set_schemas(self, schemas: list[dict[str, Any]], values: dict[str, Any]) -> None:
        while self._layout.rowCount():
            self._layout.removeRow(0)
        self._schemas = schemas
        self._editors = build_editors(
            schemas,
            values,
            self,
            decimals=self._decimals,
            single_step=self._single_step,
        )
        for schema in schemas:
            self._layout.addRow(schema.get("label", schema["id"]), self._editors[schema["id"]])
            editor = self._editors[schema["id"]]
            if isinstance(editor, QCheckBox):
                editor.toggled.connect(self._emit)
            elif isinstance(editor, QComboBox):
                editor.currentTextChanged.connect(lambda *_: self._emit())
            elif isinstance(editor, QLineEdit):
                editor.textChanged.connect(lambda *_: self._emit())
            elif isinstance(editor, QDoubleSpinBox):
                editor.valueChanged.connect(lambda *_: self._emit())

    def values(self) -> dict[str, Any]:
        return collect_values(self._schemas, self._editors)

    def _emit(self) -> None:
        self.values_changed.emit(self.values())

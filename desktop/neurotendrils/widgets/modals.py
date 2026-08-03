"""Thin in-app modal API (alert / confirm / choice / present)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QEventLoop
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.widgets.modal_host import ModalHost


def find_host(anchor: QWidget | None) -> ModalHost | None:
    """Walk parents / top-levels for a mounted ``ModalHost``."""
    widget: QWidget | None = anchor
    while widget is not None:
        host = widget.property("_ntModalHost")
        if isinstance(host, ModalHost):
            return host
        host_attr = getattr(widget, "modal_host", None)
        if isinstance(host_attr, ModalHost):
            return host_attr
        widget = widget.parentWidget()

    for top in QApplication.topLevelWidgets():
        host_attr = getattr(top, "modal_host", None)
        if isinstance(host_attr, ModalHost):
            return host_attr
        central_fn = getattr(top, "centralWidget", None)
        if callable(central_fn):
            central = central_fn()
            if isinstance(central, QWidget):
                host = central.property("_ntModalHost")
                if isinstance(host, ModalHost):
                    return host
    return None


def present(
    anchor: QWidget | None,
    widget: QWidget,
    *,
    dismissible: bool = True,
    own: bool = True,
    max_width: int = 720,
    max_height: int = 560,
) -> ModalHost | None:
    host = find_host(anchor)
    if host is None:
        return None
    host.present(
        widget,
        dismissible=dismissible,
        own=own,
        max_width=max_width,
        max_height=max_height,
    )
    return host


def _run_until(host: ModalHost) -> None:
    loop = QEventLoop(host)

    def _quit() -> None:
        if loop.isRunning():
            loop.quit()

    host.dismissed.connect(_quit)
    loop.exec()
    try:
        host.dismissed.disconnect(_quit)
    except RuntimeError:
        pass


class _MessagePanel(QWidget):
    def __init__(
        self,
        title: str,
        message: str,
        buttons: Sequence[tuple[str, str, bool]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("modalMessagePanel")
        self.choice: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        heading = QLabel(title, self)
        heading.setObjectName("modalTitle")
        body = QLabel(message, self)
        body.setObjectName("modalBody")
        body.setWordWrap(True)
        root.addWidget(heading)
        root.addWidget(body)

        row = QHBoxLayout()
        row.addStretch(1)
        for key, label, primary in buttons:
            btn = QPushButton(label, self)
            btn.setObjectName("primaryButton" if primary else "secondaryButton")
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            row.addWidget(btn)
        root.addLayout(row)

    def _pick(self, key: str) -> None:
        self.choice = key
        host = find_host(self)
        if host is not None:
            host.dismiss()


def alert(anchor: QWidget | None, title: str, message: str) -> None:
    host = find_host(anchor)
    if host is None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(anchor, title, message)
        return
    panel = _MessagePanel(title, message, (("ok", "OK", True),))
    host.present(panel, dismissible=True, own=False, max_width=440, max_height=280)
    _run_until(host)
    panel.deleteLater()


def confirm(
    anchor: QWidget | None,
    title: str,
    message: str,
    *,
    yes_label: str = "Yes",
    no_label: str = "No",
    default_yes: bool = False,
) -> bool:
    host = find_host(anchor)
    if host is None:
        from PySide6.QtWidgets import QMessageBox

        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        default = (
            QMessageBox.StandardButton.Yes
            if default_yes
            else QMessageBox.StandardButton.No
        )
        return (
            QMessageBox.question(anchor, title, message, buttons, default)
            == QMessageBox.StandardButton.Yes
        )
    panel = _MessagePanel(
        title,
        message,
        (
            ("no", no_label, False),
            ("yes", yes_label, True),
        ),
    )
    host.present(panel, dismissible=True, own=False, max_width=440, max_height=280)
    _run_until(host)
    ok = panel.choice == "yes"
    panel.deleteLater()
    return ok


class _ChoicePanel(QWidget):
    def __init__(
        self,
        title: str,
        label: str,
        items: Sequence[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("modalMessagePanel")
        self.selection: str | None = None
        self.ok = False

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(12)

        heading = QLabel(title, self)
        heading.setObjectName("modalTitle")
        hint = QLabel(label, self)
        hint.setObjectName("modalBody")
        self._list = QListWidget(self)
        self._list.setObjectName("modalChoiceList")
        self._list.addItems(list(items))
        if items:
            self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(lambda *_: self._accept())

        root.addWidget(heading)
        root.addWidget(hint)
        root.addWidget(self._list, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel", self)
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self._reject)
        ok = QPushButton("Add", self)
        ok.setObjectName("primaryButton")
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        root.addLayout(row)

    def _accept(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self.selection = item.text()
        self.ok = True
        host = find_host(self)
        if host is not None:
            host.dismiss()

    def _reject(self) -> None:
        self.ok = False
        self.selection = None
        host = find_host(self)
        if host is not None:
            host.dismiss()


def prompt_choice(
    anchor: QWidget | None,
    title: str,
    label: str,
    items: Sequence[str],
) -> tuple[str | None, bool]:
    host = find_host(anchor)
    if host is None:
        from PySide6.QtWidgets import QInputDialog

        choice, ok = QInputDialog.getItem(
            anchor, title, label, list(items), 0, False
        )
        return (choice if ok else None), bool(ok)
    panel = _ChoicePanel(title, label, items)
    host.present(panel, dismissible=True, own=False, max_width=480, max_height=420)
    _run_until(host)
    selection, ok = panel.selection, panel.ok
    panel.deleteLater()
    return selection, ok


def edit_schema(
    anchor: QWidget | None,
    title: str,
    intro: str,
    schemas: list[dict[str, Any]],
    values: dict[str, Any],
    validator: Callable[[dict[str, Any]], str | None],
    *,
    decimals: int = 3,
    single_step: float = 0.1,
) -> dict[str, Any] | None:
    """Present schema editor; return values on OK, else ``None``."""
    from neurotendrils.widgets.schema_form import SchemaEditPanel

    host = find_host(anchor)
    panel = SchemaEditPanel(
        title,
        intro,
        schemas,
        values,
        validator,
        decimals=decimals,
        single_step=single_step,
    )
    if host is None:
        from PySide6.QtWidgets import QDialog, QVBoxLayout

        dlg = QDialog(anchor)
        dlg.setWindowTitle(title)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(panel)
        result: dict[str, Any] | None = None

        def _ok(vals: dict[str, Any]) -> None:
            nonlocal result
            result = vals
            dlg.accept()

        panel.accepted.connect(_ok)
        panel.rejected.connect(dlg.reject)
        dlg.exec()
        return result

    result_box: dict[str, Any] = {"values": None}

    def _ok(vals: dict[str, Any]) -> None:
        result_box["values"] = vals
        host.dismiss()

    panel.accepted.connect(_ok)
    panel.rejected.connect(host.dismiss)
    host.present(panel, dismissible=True, own=False, max_width=480, max_height=560)
    _run_until(host)
    values = result_box["values"]
    panel.deleteLater()
    return values

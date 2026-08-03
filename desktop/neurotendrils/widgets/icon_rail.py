"""Expandable icon navigation rail for the app shell."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme
from neurotendrils.widgets.icons import Glyph, avatar, icon
from neurotendrils.widgets.motion import DURATION_NORMAL, animate_opacity, animate_width


COLLAPSED_WIDTH = 56
EXPANDED_WIDTH = 200


@dataclass(frozen=True)
class RailItem:
    key: str
    label: str
    glyph: Glyph


class _RailRow(QWidget):
    """Full-row hit target so labels are clickable when expanded."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("railRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class IconRail(QWidget):
    """Icon rail with NeuroTendrils word mark; chevron expands labels."""

    currentChanged = Signal(int)
    settingsRequested = Signal()

    def __init__(
        self,
        items: list[RailItem],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("iconRail")
        self.setFixedWidth(COLLAPSED_WIDTH)

        self._items = items
        self._index = 0
        self._expanded = False
        self._buttons: list[QToolButton] = []
        self._labels: list[QLabel] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 18, 12, 12)
        root.setSpacing(2)

        self._brand = QWidget(self)
        self._brand.setObjectName("railBrand")
        brand_l = QHBoxLayout(self._brand)
        brand_l.setContentsMargins(6, 0, 4, 0)
        brand_l.setSpacing(0)
        neuro = QLabel("Neuro", self._brand)
        neuro.setObjectName("brandNeuro")
        tendrils = QLabel("Tendrils", self._brand)
        tendrils.setObjectName("brandTendrils")
        brand_l.addWidget(neuro)
        brand_l.addWidget(tendrils)
        brand_l.addStretch(1)
        self._brand.hide()
        root.addWidget(self._brand)
        root.addSpacing(8)

        self._nav_host = QWidget(self)
        nav = QVBoxLayout(self._nav_host)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(4)

        for i, item in enumerate(items):
            row = _RailRow(self._nav_host)
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(10)

            btn = QToolButton(row)
            btn.setObjectName("railNavButton")
            btn.setCheckable(True)
            btn.setAutoRaise(True)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setIconSize(QSize(18, 18))
            btn.setFixedSize(32, 32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(item.label)
            btn.setAccessibleName(item.label)
            # Let the row own the click; keep the button visual/checked state.
            btn.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._group.addButton(btn, i)

            label = QLabel(item.label, row)
            label.setObjectName("railNavLabel")
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            label.hide()

            row_l.addWidget(btn, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row_l.addWidget(label, 1)
            row.clicked.connect(lambda idx=i: self.set_current(idx))
            nav.addWidget(row)
            self._buttons.append(btn)
            self._labels.append(label)

        nav.addStretch(1)
        root.addWidget(self._nav_host, 1)

        footer = QWidget(self)
        footer.setObjectName("railFooter")
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(0, 8, 0, 0)
        foot.setSpacing(6)

        self._expand_btn = QPushButton(footer)
        self._expand_btn.setObjectName("railExpandButton")
        self._expand_btn.setFlat(True)
        self._expand_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.clicked.connect(self.toggle_expanded)
        self._sync_expand_button()
        foot.addWidget(self._expand_btn, 0, Qt.AlignmentFlag.AlignHCenter)

        self._user_row = QWidget(footer)
        user_l = QHBoxLayout(self._user_row)
        user_l.setContentsMargins(0, 0, 0, 0)
        user_l.setSpacing(10)

        self._avatar_btn = QToolButton(self._user_row)
        self._avatar_btn.setObjectName("railAvatarButton")
        self._avatar_btn.setAutoRaise(True)
        self._avatar_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._avatar_btn.setFixedSize(32, 32)
        self._avatar_btn.setIconSize(QSize(28, 28))
        self._avatar_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._avatar_btn.setToolTip("Settings · 0 MB of 1 GB")
        self._avatar_btn.setAccessibleName("Open settings")
        self._avatar_btn.clicked.connect(self.settingsRequested.emit)

        self._user_meta = QWidget(self._user_row)
        self._user_meta.setObjectName("railUserMeta")
        meta = QVBoxLayout(self._user_meta)
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(2)
        name = QLabel("Guest", self._user_meta)
        name.setObjectName("userName")
        self._storage_bar = QProgressBar(self._user_meta)
        self._storage_bar.setObjectName("storageBar")
        self._storage_bar.setRange(0, 1024)
        self._storage_bar.setValue(0)
        self._storage_bar.setTextVisible(False)
        self._storage_bar.setFixedHeight(4)
        self._storage = QLabel("0 MB of 1 GB", self._user_meta)
        self._storage.setObjectName("userStorage")
        meta.addWidget(name)
        meta.addWidget(self._storage_bar)
        meta.addWidget(self._storage)
        self._user_meta.hide()

        user_l.addWidget(self._avatar_btn, 0, Qt.AlignmentFlag.AlignLeft)
        user_l.addWidget(self._user_meta, 1)
        foot.addWidget(self._user_row)
        root.addWidget(footer)

        if self._buttons:
            self._buttons[0].setChecked(True)
            self._sync_label_styles()

        Theme.instance().changed.connect(self.apply_chrome)
        self.apply_chrome()

    def current_index(self) -> int:
        return self._index

    def set_current(self, index: int) -> None:
        if index < 0 or index >= len(self._buttons):
            return
        changed = index != self._index
        self._index = index
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self._sync_label_styles()
        if changed:
            self.currentChanged.emit(index)

    def _sync_label_styles(self) -> None:
        for i, label in enumerate(self._labels):
            label.setObjectName(
                "railNavLabelSelected" if i == self._index else "railNavLabel"
            )
            label.style().unpolish(label)
            label.style().polish(label)

    def toggle_expanded(self) -> None:
        self._set_expanded(not self._expanded)

    def _sync_expand_button(self) -> None:
        footer_layout = self._expand_btn.parentWidget().layout() if self._expand_btn.parentWidget() else None
        if self._expanded:
            self._expand_btn.setObjectName("railExpandButton")
            self._expand_btn.setText("Collapse")
            tip = "Collapse navigation"
            # Clear any prior fixed size from the collapsed chevron state.
            self._expand_btn.setMinimumSize(0, 0)
            self._expand_btn.setMaximumSize(16777215, 16777215)
            if footer_layout is not None:
                footer_layout.setAlignment(self._expand_btn, Qt.AlignmentFlag.AlignLeft)
        else:
            self._expand_btn.setObjectName("railExpandChevron")
            self._expand_btn.setText("›")
            tip = "Expand navigation"
            self._expand_btn.setFixedSize(32, 32)
            if footer_layout is not None:
                footer_layout.setAlignment(self._expand_btn, Qt.AlignmentFlag.AlignHCenter)
        self._expand_btn.setToolTip(tip)
        self._expand_btn.setAccessibleName(tip)
        self._expand_btn.style().unpolish(self._expand_btn)
        self._expand_btn.style().polish(self._expand_btn)

    def apply_chrome(self) -> None:
        theme = Theme.instance()
        normal = theme.muted_text_color()
        selected = theme.text_color()
        for btn, item in zip(self._buttons, self._items, strict=True):
            btn.setIcon(icon(item.glyph, normal, selected))

        bg = theme.muted_text_color()
        bg.setAlpha(60)
        screen = self.screen() or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        pm = avatar(28, bg, theme.muted_text_color(), dpr)
        av = QIcon()
        av.addPixmap(pm)
        self._avatar_btn.setIcon(av)

    def _set_expanded(self, expanded: bool) -> None:
        target = EXPANDED_WIDTH if expanded else COLLAPSED_WIDTH
        if expanded == self._expanded and self.width() == target:
            return
        self._expanded = expanded
        self._sync_expand_button()
        animate_width(self, target, duration=DURATION_NORMAL)

        if expanded:
            self._brand.show()
            animate_opacity(self._brand, 1.0, duration=DURATION_NORMAL)
        else:
            self._brand.hide()

        for label in self._labels:
            if expanded:
                label.show()
                animate_opacity(label, 1.0, duration=DURATION_NORMAL)
            else:
                label.hide()

        if expanded:
            self._user_meta.show()
            animate_opacity(self._user_meta, 1.0, duration=DURATION_NORMAL)
        else:
            self._user_meta.hide()

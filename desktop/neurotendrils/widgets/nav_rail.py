"""Collapsible left navigation rail."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme
from neurotendrils.widgets.icons import Glyph, brand_mark, single_icon
from neurotendrils.widgets.motion import DURATION_NORMAL, animate_width

COLLAPSED_WIDTH = 56
EXPANDED_WIDTH = 216

_ITEM_HEIGHT = 32
_ICON = 18


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    glyph: Glyph


class NavRail(QWidget):
    """Icon navigation with optional labels; emits the activated item key."""

    itemActivated = Signal(str)

    def __init__(
        self,
        items: list[NavItem],
        footer_items: list[NavItem] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("navRail")
        self.setFixedWidth(COLLAPSED_WIDTH)

        self._items: list[NavItem] = list(items) + list(footer_items or [])
        self._buttons: dict[str, QToolButton] = {}
        self._expanded = False
        self._current = items[0].key if items else ""

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 16, 10, 12)
        root.setSpacing(8)

        root.addWidget(self._build_brand())
        root.addSpacing(8)

        primary = QWidget(self)
        primary_layout = QVBoxLayout(primary)
        primary_layout.setContentsMargins(0, 0, 0, 0)
        primary_layout.setSpacing(2)
        for item in items:
            primary_layout.addWidget(self._build_item(item, primary))
        root.addWidget(primary)
        root.addStretch(1)

        if footer_items:
            footer = QWidget(self)
            footer_layout = QVBoxLayout(footer)
            footer_layout.setContentsMargins(0, 0, 0, 0)
            footer_layout.setSpacing(2)
            for item in footer_items:
                footer_layout.addWidget(self._build_item(item, footer))
            root.addWidget(footer)

        self._toggle = QToolButton(self)
        self._toggle.setObjectName("navToggle")
        self._toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setFixedHeight(_ITEM_HEIGHT - 4)
        self._toggle.setIconSize(QSize(16, 16))
        self._toggle.clicked.connect(self.toggle_expanded)
        root.addWidget(self._toggle)

        self._group.idClicked.connect(self._on_clicked)
        self.set_current(self._current)
        Theme.instance().changed.connect(self.apply_chrome)
        self.apply_chrome()

    # ---------- construction ----------

    def _build_brand(self) -> QWidget:
        brand = QWidget(self)
        layout = QHBoxLayout(brand)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(8)
        self._brand_mark = QLabel(brand)
        self._brand_mark.setObjectName("navBrandMark")
        self._brand_mark.setFixedSize(26, 26)
        self._brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._brand_word = QLabel("NeuroTendrils", brand)
        self._brand_word.setObjectName("navBrand")
        self._brand_word.hide()
        layout.addWidget(self._brand_mark, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._brand_word, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        return brand

    def _build_item(self, item: NavItem, parent: QWidget) -> QToolButton:
        button = QToolButton(parent)
        button.setObjectName("navItem")
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(_ICON, _ICON))
        button.setFixedHeight(_ITEM_HEIGHT)
        button.setText(item.label)
        button.setToolTip(item.label)
        button.setAccessibleName(item.label)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setProperty("navKey", item.key)
        self._group.addButton(button, len(self._buttons))
        self._buttons[item.key] = button
        return button

    # ---------- state ----------

    def current_key(self) -> str:
        return self._current

    def set_current(self, key: str) -> None:
        if key not in self._buttons:
            return
        self._current = key
        for item_key, button in self._buttons.items():
            button.setChecked(item_key == key)
        self.apply_chrome()

    def is_expanded(self) -> bool:
        return self._expanded

    def toggle_expanded(self) -> None:
        self._set_expanded(not self._expanded)

    def _on_clicked(self, index: int) -> None:
        button = self._group.button(index)
        if button is None:
            return
        key = str(button.property("navKey") or "")
        if key:
            self.itemActivated.emit(key)

    def _set_expanded(self, expanded: bool) -> None:
        target = EXPANDED_WIDTH if expanded else COLLAPSED_WIDTH
        if expanded == self._expanded and self.width() == target:
            return
        self._expanded = expanded
        style = (
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            if expanded
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        for button in self._buttons.values():
            button.setToolButtonStyle(style)
        self._brand_mark.setVisible(not expanded)
        self._brand_word.setVisible(expanded)
        self._sync_toggle()
        animate_width(self, target, duration=DURATION_NORMAL)

    def _sync_toggle(self) -> None:
        label = "Collapse" if self._expanded else ""
        tip = "Collapse navigation" if self._expanded else "Expand navigation"
        self._toggle.setText(label)
        self._toggle.setToolTip(tip)
        self._toggle.setAccessibleName(tip)
        self._toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
            if self._expanded
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        theme = Theme.instance()
        glyph = Glyph.CHEVRON_LEFT if self._expanded else Glyph.CHEVRON_RIGHT
        self._toggle.setIcon(single_icon(glyph, theme.muted_text_color(), 16))

    def apply_chrome(self) -> None:
        theme = Theme.instance()
        muted = theme.muted_text_color()
        accent = theme.accent_color()
        for item in self._items:
            button = self._buttons.get(item.key)
            if button is None:
                continue
            color = accent if item.key == self._current else muted
            button.setIcon(single_icon(item.glyph, color, _ICON))
        self._sync_brand()
        self._sync_toggle()

    def _sync_brand(self) -> None:
        """NT plate: accent fill with light letters in both themes."""
        theme = Theme.instance()
        screen = self.screen() or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        # Always light ink — dark accentText on the dark-theme blue plate looked
        # like a light-mode badge dropped into a dark chrome.
        ink = QColor("#ffffff")
        self._brand_mark.setPixmap(brand_mark(26, theme.accent_color(), ink, dpr))

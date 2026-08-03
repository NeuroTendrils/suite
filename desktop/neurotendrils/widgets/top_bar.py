"""Application top bar: context title, search, notifications, profile."""

from __future__ import annotations

import sys

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

from neurotendrils.core.theme import Theme
from neurotendrils.widgets.icons import Glyph, avatar, single_icon

_BAR_HEIGHT = 48


def _search_hint() -> str:
    return "⌘K" if sys.platform == "darwin" else "Ctrl K"


class TopBar(QWidget):
    searchChanged = Signal(str)
    searchSubmitted = Signal(str)
    notificationsRequested = Signal()
    profileRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(_BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 16, 0)
        layout.setSpacing(16)

        self._title = QLabel("", self)
        self._title.setObjectName("topBarTitle")

        search_host = QWidget(self)
        search_host.setFixedWidth(320)
        search_layout = QHBoxLayout(search_host)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)

        self._search = QLineEdit(search_host)
        self._search.setObjectName("searchField")
        self._search.setPlaceholderText("Search this project")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(28)
        # Avoid stealing focus at launch; Cmd/Ctrl+F still focuses it explicitly.
        self._search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._search.textChanged.connect(self.searchChanged.emit)
        self._search.returnPressed.connect(
            lambda: self.searchSubmitted.emit(self._search.text())
        )
        search_layout.addWidget(self._search)

        self._hint = QLabel(_search_hint(), self._search)
        self._hint.setObjectName("searchHint")
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._notifications = QToolButton(self)
        self._notifications.setObjectName("iconButton")
        self._notifications.setAutoRaise(True)
        self._notifications.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._notifications.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notifications.setFixedSize(28, 28)
        self._notifications.setIconSize(QSize(17, 17))
        self._notifications.setToolTip("Notifications")
        self._notifications.setAccessibleName("Notifications")
        self._notifications.clicked.connect(self.notificationsRequested.emit)

        self._profile = QToolButton(self)
        self._profile.setObjectName("avatarButton")
        self._profile.setAutoRaise(True)
        self._profile.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile.setFixedSize(28, 28)
        self._profile.setIconSize(QSize(24, 24))
        self._profile.setToolTip("Guest · Settings")
        self._profile.setAccessibleName("Profile and settings")
        self._profile.clicked.connect(self.profileRequested.emit)

        layout.addWidget(self._title)
        layout.addWidget(search_host)
        layout.addStretch(1)
        layout.addWidget(self._notifications)
        layout.addWidget(self._profile)

        Theme.instance().changed.connect(self.apply_chrome)
        self.apply_chrome()

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_title_tooltip(self, tooltip: str) -> None:
        self._title.setToolTip(tooltip)

    def search_text(self) -> str:
        return self._search.text()

    def clear_search(self) -> None:
        self._search.clear()

    def focus_search(self) -> None:
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()

    def apply_chrome(self) -> None:
        theme = Theme.instance()
        muted = theme.muted_text_color()
        self._notifications.setIcon(single_icon(Glyph.NOTIFICATIONS, muted, 17))

        fill = theme.muted_text_color()
        fill.setAlpha(48)
        screen = self.screen() or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        badge = QIcon()
        badge.addPixmap(avatar(24, fill, muted, dpr))
        self._profile.setIcon(badge)

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._position_hint()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._position_hint()

    def _position_hint(self) -> None:
        self._hint.adjustSize()
        margin = 30 if self._search.isClearButtonEnabled() else 10
        x = max(0, self._search.width() - self._hint.width() - margin)
        y = (self._search.height() - self._hint.height()) // 2
        self._hint.move(x, y)

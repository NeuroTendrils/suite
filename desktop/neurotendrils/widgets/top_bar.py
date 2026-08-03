"""Application top bar: project switcher, search, notifications, profile."""

from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from neurotendrils.core.notifications import NotificationCenter
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.core.theme import Theme
from neurotendrils.widgets.icons import Glyph, avatar, single_icon

_BAR_HEIGHT = 56
_SEARCH_HEIGHT = 36
_SEARCH_PAD_X = 12
_SEARCH_PAD_CLEAR = 28


def _search_hint() -> str:
    return "⌘K" if sys.platform == "darwin" else "Ctrl K"


class TopBar(QWidget):
    searchChanged = Signal(str)
    searchSubmitted = Signal(str)
    notificationsRequested = Signal()
    profileRequested = Signal()
    projectSwitchRequested = Signal(str)
    browseFolderRequested = Signal()
    manageProjectsRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(_BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 10, 16, 10)
        layout.setSpacing(14)

        self._project = QToolButton(self)
        self._project.setObjectName("projectSwitcher")
        self._project.setAutoRaise(True)
        self._project.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._project.setCursor(Qt.CursorShape.PointingHandCursor)
        self._project.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._project.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._project.setMaximumWidth(220)
        self._project.setFixedHeight(_SEARCH_HEIGHT)
        self._menu = QMenu(self._project)
        self._menu.setObjectName("projectMenu")
        self._project.setMenu(self._menu)
        self._menu.aboutToShow.connect(self._rebuild_project_menu)

        # Border/background live on the shell; the line edit is borderless so
        # Qt/macOS stylesheet padding cannot clip ascenders.
        self._search_host = QFrame(self)
        self._search_host.setObjectName("searchShell")
        self._search_host.setFixedSize(380, _SEARCH_HEIGHT)
        search_layout = QHBoxLayout(self._search_host)
        search_layout.setContentsMargins(_SEARCH_PAD_X, 0, 8, 0)
        search_layout.setSpacing(0)

        self._search = QLineEdit(self._search_host)
        self._search.setObjectName("searchInput")
        self._search.setPlaceholderText("Search project files")
        self._search.setClearButtonEnabled(True)
        self._search.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._search.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self._search.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._search.setTextMargins(0, 0, _SEARCH_PAD_CLEAR, 0)
        # Fill the shell — preferred height alone sits too short and looks clipped.
        self._search.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._search.textChanged.connect(self._on_search_text)
        self._search.returnPressed.connect(
            lambda: self.searchSubmitted.emit(self._search.text())
        )
        self._search.installEventFilter(self)
        search_layout.addWidget(self._search)

        self._hint = QLabel(_search_hint(), self._search)
        self._hint.setObjectName("searchHint")
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._notify_host = QWidget(self)
        self._notify_host.setFixedSize(28, 28)
        self._notifications = QToolButton(self._notify_host)
        self._notifications.setObjectName("iconButton")
        self._notifications.setAutoRaise(True)
        self._notifications.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._notifications.setCursor(Qt.CursorShape.PointingHandCursor)
        self._notifications.setFixedSize(28, 28)
        self._notifications.setIconSize(QSize(17, 17))
        self._notifications.setToolTip("Notifications")
        self._notifications.setAccessibleName("Notifications")
        self._notifications.clicked.connect(self.notificationsRequested.emit)
        self._badge = QLabel(self._notify_host)
        self._badge.setObjectName("notificationBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.hide()
        self._badge.move(16, 0)

        self._profile = QToolButton(self)
        self._profile.setObjectName("avatarButton")
        self._profile.setAutoRaise(True)
        self._profile.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self._profile.setFixedSize(28, 28)
        self._profile.setIconSize(QSize(24, 24))
        self._profile.setToolTip("Account")
        self._profile.setAccessibleName("Account")
        self._profile.clicked.connect(self.profileRequested.emit)

        layout.addWidget(self._project, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._search_host, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        layout.addWidget(self._notify_host, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._profile, 0, Qt.AlignmentFlag.AlignVCenter)

        Theme.instance().changed.connect(self.apply_chrome)
        NotificationCenter.instance().changed.connect(self._sync_badge)
        ProjectDir.instance().root_changed.connect(lambda *_: self.refresh_project())
        self.apply_chrome()
        self._sync_badge()
        self.refresh_project()

    def refresh_project(self) -> None:
        from pathlib import Path

        root = ProjectDir.instance().root
        name = Path(root).name if root else "No project"
        metrics = self._project.fontMetrics()
        label = metrics.elidedText(name, Qt.TextElideMode.ElideRight, 200)
        self._project.setText(f"{label} ▾")
        self._project.setToolTip(root or "Open a project")

    def set_title(self, title: str) -> None:
        # Kept for callers; project name comes from ProjectDir.
        del title
        self.refresh_project()

    def set_title_tooltip(self, tooltip: str) -> None:
        self._project.setToolTip(tooltip)

    def search_text(self) -> str:
        return self._search.text()

    def clear_search(self) -> None:
        self._search.clear()
        self._sync_hint()

    def focus_search(self) -> None:
        self._search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._search.selectAll()
        self._sync_hint()

    def search_global_rect(self) -> QRect:
        return QRect(
            self._search_host.mapToGlobal(QPoint(0, 0)), self._search_host.size()
        )

    def notify_global_rect(self) -> QRect:
        return QRect(
            self._notify_host.mapToGlobal(QPoint(0, 0)), self._notify_host.size()
        )

    def _on_search_text(self, text: str) -> None:
        self._sync_hint()
        self.searchChanged.emit(text)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._search and event.type() in (
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        ):
            focused = event.type() == QEvent.Type.FocusIn
            self._search_host.setProperty("focused", "true" if focused else "false")
            style = self._search_host.style()
            style.unpolish(self._search_host)
            style.polish(self._search_host)
            self._search_host.update()
            # Defer so hasFocus() reflects the new state.
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._sync_hint)
        return super().eventFilter(watched, event)

    def _sync_hint(self) -> None:
        # Hide the shortcut chip while typing so it never clips the query.
        busy = bool(self._search.text()) or self._search.hasFocus()
        self._hint.setVisible(not busy)
        self._position_hint()

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

    def _rebuild_project_menu(self) -> None:
        self._menu.clear()
        project = ProjectDir.instance()
        active = project.root
        for info in project.list_projects():
            action = self._menu.addAction(info.name)
            action.setCheckable(True)
            action.setChecked(info.path == active)
            action.triggered.connect(
                lambda _=False, path=info.path: self.projectSwitchRequested.emit(path)
            )
        self._menu.addSeparator()
        browse = self._menu.addAction("Browse folder…")
        browse.triggered.connect(self.browseFolderRequested.emit)
        manage = self._menu.addAction("Manage projects…")
        manage.triggered.connect(self.manageProjectsRequested.emit)

    def _sync_badge(self) -> None:
        count = NotificationCenter.instance().unread_count()
        if count <= 0:
            self._badge.hide()
            return
        self._badge.setText("9+" if count > 9 else str(count))
        self._badge.adjustSize()
        self._badge.move(max(0, 28 - self._badge.width()), 0)
        self._badge.show()
        self._badge.raise_()

    def resizeEvent(self, event) -> None:  # noqa: ANN001, N802
        super().resizeEvent(event)
        self._position_hint()

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._position_hint()

    def _position_hint(self) -> None:
        if not self._hint.isVisible():
            return
        self._hint.adjustSize()
        # Leave room for the clear button on the trailing edge.
        margin = 34 if self._search.isClearButtonEnabled() else 12
        x = max(0, self._search.width() - self._hint.width() - margin)
        y = max(0, (self._search.height() - self._hint.height()) // 2)
        self._hint.move(x, y)

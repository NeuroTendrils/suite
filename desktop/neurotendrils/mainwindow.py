from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme
from neurotendrils.modules.hub.page import HubPage
from neurotendrils.modules.neuroflow.page import NeuroFlowPage
from neurotendrils.modules.neurostudio.page import NeuroStudioPage
from neurotendrils.settingsdialog import SettingsDialog
from neurotendrils.widgets.icons import Glyph, avatar, icon


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NeuroTendrils")
        self.resize(1024, 720)
        self.setMinimumSize(720, 480)
        self._settings: SettingsDialog | None = None

        root = QWidget(self)
        root.setObjectName("appRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget(root)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 22, 16, 0)
        side.setSpacing(6)

        brand = QWidget(sidebar)
        brand_l = QHBoxLayout(brand)
        brand_l.setContentsMargins(10, 0, 0, 18)
        brand_l.setSpacing(0)
        neuro = QLabel("Neuro", brand)
        neuro.setObjectName("brandNeuro")
        tendrils = QLabel("Tendrils", brand)
        tendrils.setObjectName("brandTendrils")
        brand_l.addWidget(neuro)
        brand_l.addWidget(tendrils)
        brand_l.addStretch(1)

        self._nav = QListWidget(sidebar)
        self._nav.setObjectName("moduleNavigation")
        self._nav.setAccessibleName("Module navigation")
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setIconSize(QSize(18, 18))
        for name in ("NeuroFlow", "NeuroStudio", "Hub"):
            self._nav.addItem(QListWidgetItem(name))

        user_card = QWidget(sidebar)
        user_card.setObjectName("userCard")
        user_l = QHBoxLayout(user_card)
        user_l.setContentsMargins(10, 14, 6, 14)
        user_l.setSpacing(12)

        self._avatar = QLabel(user_card)
        self._avatar.setFixedSize(32, 32)

        user_text = QWidget(user_card)
        ut = QVBoxLayout(user_text)
        ut.setContentsMargins(0, 0, 0, 0)
        ut.setSpacing(1)
        name = QLabel("Guest", user_text)
        name.setObjectName("userName")
        storage_bar = QProgressBar(user_text)
        storage_bar.setObjectName("storageBar")
        storage_bar.setRange(0, 1024)
        storage_bar.setValue(0)
        storage_bar.setTextVisible(False)
        storage_bar.setFixedHeight(4)
        storage = QLabel("0 MB of 1 GB", user_text)
        storage.setObjectName("userStorage")
        ut.addWidget(name)
        ut.addSpacing(3)
        ut.addWidget(storage_bar)
        ut.addSpacing(2)
        ut.addWidget(storage)

        self._settings_btn = QToolButton(user_card)
        self._settings_btn.setObjectName("settingsButton")
        self._settings_btn.setAccessibleName("Open settings")
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.setAutoRaise(True)
        self._settings_btn.setText("")
        self._settings_btn.setIconSize(QSize(18, 18))
        self._settings_btn.clicked.connect(self.open_settings)

        user_l.addWidget(self._avatar)
        user_l.addWidget(user_text, 1)
        user_l.addWidget(self._settings_btn)

        side.addWidget(brand)
        side.addWidget(self._nav, 1)
        side.addWidget(user_card)

        self._pages = QStackedWidget(root)
        self._pages.addWidget(NeuroFlowPage(self._pages))
        self._pages.addWidget(NeuroStudioPage(self._pages))
        self._pages.addWidget(HubPage(self._pages))

        layout.addWidget(sidebar)
        layout.addWidget(self._pages, 1)
        self.setCentralWidget(root)

        self._nav.currentRowChanged.connect(self._pages.setCurrentIndex)
        Theme.instance().changed.connect(self.apply_chrome)
        self.apply_chrome()
        self._nav.setCurrentRow(0)

    def apply_chrome(self) -> None:
        theme = Theme.instance()
        normal = theme.muted_text_color()
        selected = theme.text_color()

        glyphs = (Glyph.FLOW, Glyph.STUDIO, Glyph.HUB)
        for row, glyph in enumerate(glyphs):
            item = self._nav.item(row)
            if item is not None:
                item.setIcon(icon(glyph, normal, selected))

        self._settings_btn.setIcon(icon(Glyph.SETTINGS, normal, selected))

        bg = theme.muted_text_color()
        bg.setAlpha(60)
        screen = self.screen() or QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        self._avatar.setPixmap(avatar(32, bg, theme.muted_text_color(), dpr))

    def open_settings(self) -> None:
        if self._settings is None:
            self._settings = SettingsDialog(self)
        self._settings.open()

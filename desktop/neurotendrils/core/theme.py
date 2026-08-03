"""Application theme"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from neurotendrils.core.projectdir import APP, ORG

THEME_KEY = "appearance/theme"


class ThemeMode(Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


@dataclass(frozen=True)
class ThemeColors:
    background: str
    sidebar: str
    selection: str
    text: str
    muted_text: str
    border: str
    accent: str
    accent_hover: str
    accent_text: str
    error: str


def colors_for(dark: bool) -> ThemeColors:
    if dark:
        return ThemeColors(
            background="#0b0d13",
            sidebar="#10131a",
            selection="#20242e",
            text="#e8eaf1",
            muted_text="#9ca3b5",
            border="#252a36",
            accent="#7795f8",
            accent_hover="#8ca6ff",
            accent_text="#0b0d13",
            error="#f06a78",
        )
    return ThemeColors(
        background="#ffffff",
        sidebar="#f7f8fa",
        selection="#eceef1",
        text="#1b1f35",
        muted_text="#687086",
        border="#e2e5eb",
        accent="#3758bc",
        accent_hover="#2f4fac",
        accent_text="#ffffff",
        error="#c83f52",
    )


_STYLE = """
QMainWindow, QWidget#appRoot {
    background-color: @background;
    color: @text;
}
QWidget#sidebar, QWidget#iconRail {
    background-color: @sidebar;
    border-right: 1px solid @border;
}
QLabel#brandNeuro, QLabel#brandTendrils {
    font-size: 15px;
    font-weight: 700;
}
QLabel#brandNeuro { color: @accent; }
QLabel#brandTendrils { color: @text; }
QPushButton#railExpandButton {
    background: transparent;
    color: @mutedText;
    border: none;
    border-radius: 0;
    outline: none;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 0;
    text-align: left;
    min-width: 0;
    min-height: 0;
}
QPushButton#railExpandButton:hover,
QPushButton#railExpandButton:pressed,
QPushButton#railExpandButton:focus {
    background: transparent;
    border: none;
    outline: none;
    color: @text;
    font-weight: 700;
}
QPushButton#railExpandChevron {
    background: transparent;
    color: @mutedText;
    border: none;
    border-radius: 0;
    outline: none;
    font-size: 22px;
    font-weight: 500;
    padding: 0;
    min-width: 0;
    min-height: 0;
}
QPushButton#railExpandChevron:hover,
QPushButton#railExpandChevron:pressed,
QPushButton#railExpandChevron:focus {
    background: transparent;
    border: none;
    outline: none;
    color: @text;
    font-weight: 700;
}
QToolButton#railNavButton {
    background: transparent;
    border: none;
    border-radius: 0;
    outline: none;
    padding: 0;
}
QToolButton#railNavButton:hover,
QToolButton#railNavButton:checked,
QToolButton#railNavButton:pressed {
    background: transparent;
    border: none;
}
QLabel#railNavLabel {
    color: @mutedText;
    font-size: 13px;
    font-weight: 500;
}
QLabel#railNavLabelSelected {
    color: @text;
    font-size: 13px;
    font-weight: 700;
}
QWidget#railFooter { border-top: 1px solid @border; }
QToolButton#railAvatarButton {
    background: transparent;
    border: none;
    border-radius: 16px;
    outline: none;
    padding: 0;
}
QToolButton#railAvatarButton:hover,
QToolButton#railAvatarButton:pressed {
    background: transparent;
}
QLabel#userName { color: @text; font-size: 13px; font-weight: 600; }
QLabel#userStorage { color: @mutedText; font-size: 11px; }
QProgressBar#storageBar {
    background-color: @selection;
    border: none;
    border-radius: 2px;
}
QProgressBar#storageBar::chunk {
    background-color: @accent;
    border-radius: 2px;
}
QLabel#pageTitle { color: @text; font-size: 22px; font-weight: 700; }
QLabel#pageDescription { color: @mutedText; font-size: 13px; }
QWidget#settingsSidebar {
    background-color: @sidebar;
    border-right: 1px solid @border;
}
QLabel#settingsNavTitle { color: @mutedText; font-size: 15px; font-weight: 600; }
QListWidget#settingsNav {
    background: transparent;
    border: none;
    outline: none;
    font-size: 14px;
}
QListWidget#settingsNav::item {
    background: transparent;
    color: @mutedText;
    border: none;
    padding: 8px 8px;
}
QListWidget#settingsNav::item:hover { color: @text; }
QListWidget#settingsNav::item:selected {
    background: transparent;
    color: @text;
    font-weight: 600;
}
QLabel#groupLabel { color: @text; font-size: 15px; font-weight: 500; }
QLabel#settingTitle { color: @text; font-size: 13px; font-weight: 600; }
QLabel#settingDescription { color: @mutedText; font-size: 12px; }
QScrollArea#pageScroll { background: transparent; border: none; }
QWidget#pageContent { background: transparent; }
QFrame#emptyPanel {
    background-color: @sidebar;
    border: 1px dashed @border;
    border-radius: 12px;
}
QFrame#filePanel, QFrame#fingerprintPanel,
QFrame#libraryPanel, QFrame#detailPanel {
    background-color: @sidebar;
    border: 1px solid @border;
    border-radius: 12px;
}
QStackedWidget#pageStack { background: transparent; }
QWidget#modalHost {
    background-color: rgba(10, 12, 18, 160);
}
QFrame#modalPanel {
    background-color: @background;
    border: 1px solid @border;
    border-radius: 14px;
}
QWidget#settingsPanel, QWidget#schemaEditPanel, QWidget#modalMessagePanel {
    background: transparent;
    border: none;
}
QLabel#modalTitle {
    color: @text;
    font-size: 18px;
    font-weight: 700;
}
QLabel#modalBody {
    color: @mutedText;
    font-size: 13px;
}
QListWidget#modalChoiceList {
    background: @sidebar;
    border: 1px solid @border;
    border-radius: 10px;
    outline: none;
    padding: 4px;
}
QListWidget#modalChoiceList::item {
    color: @text;
    border: none;
    border-radius: 6px;
    padding: 8px 10px;
}
QListWidget#modalChoiceList::item:selected {
    background: transparent;
    color: @text;
    font-weight: 700;
}
QListWidget#modalChoiceList::item:hover {
    color: @text;
    font-weight: 700;
}
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {
    background-color: @sidebar;
    color: @text;
    border: 1px solid @border;
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 20px;
    selection-background-color: @accent;
    selection-color: @accentText;
}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QLineEdit:focus {
    border: 1px solid @accent;
    outline: none;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background-color: @background;
    color: @text;
    border: 1px solid @border;
    selection-background-color: @selection;
    selection-color: @text;
    outline: none;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QSpinBox::up-button, QSpinBox::down-button {
    background: transparent;
    border: none;
    width: 16px;
}
QLabel#emptyPanelTitle { color: @text; font-size: 15px; font-weight: 600; }
QLabel#emptyPanelHint { color: @mutedText; font-size: 12px; }
QLabel#fileNameLabel { color: @text; font-size: 14px; font-weight: 600; }
QLabel#fileMetaLabel { color: @mutedText; font-size: 12px; }
QLabel#filePathLabel {
    color: @mutedText;
    font-size: 11px;
    font-family: Menlo, Monaco, Consolas, monospace;
}
QLabel#fingerprintKey { color: @mutedText; font-size: 11px; }
QLabel#fingerprintValue { color: @text; font-size: 13px; font-weight: 600; }
QLabel#fingerprintChannels { color: @mutedText; font-size: 12px; }
QFrame#planStepRow, QFrame#templateRow, QFrame#libraryRow {
    background-color: @background;
    border: 1px solid @border;
    border-radius: 8px;
}
QLabel#planStepIndex {
    color: @accent;
    background-color: @selection;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#planStepTitle, QLabel#templateTitle { color: @text; font-size: 13px; font-weight: 600; }
QLabel#planStepMeta, QLabel#templateMeta {
    color: @mutedText;
    font-size: 11px;
    font-family: Menlo, Monaco, Consolas, monospace;
}
QLabel#planStepRationale, QLabel#templateRationale { color: @mutedText; font-size: 11px; }
QPushButton#planStepButton, QPushButton#secondaryButton {
    background: transparent;
    color: @text;
    border: 1px solid @border;
    border-radius: 7px;
    padding: 6px 12px;
    font-size: 12px;
    /* Keep weight constant so hover highlight doesn't resize the label. */
    font-weight: 700;
    outline: none;
}
QPushButton#planStepButton {
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    min-width: 0;
    min-height: 0;
}
QPushButton#planStepButton:hover, QPushButton#secondaryButton:hover {
    background-color: @selection;
    color: @text;
}
QPushButton#planStepButton:focus, QPushButton#secondaryButton:focus,
QPushButton#planStepButton:pressed, QPushButton#secondaryButton:pressed {
    background: transparent;
    border: 1px solid @border;
    outline: none;
}
QPushButton#secondaryButton:hover:focus {
    background-color: @selection;
    outline: none;
}
QPushButton#planStepButton:disabled, QPushButton#secondaryButton:disabled {
    color: @mutedText;
    border-color: @border;
}
QLabel#stepEditError { color: #c45c5c; font-size: 12px; }
QPushButton#primaryButton {
    background-color: @accent;
    color: @accentText;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 600;
    min-width: 110px;
    outline: none;
}
QPushButton#primaryButton:hover { background-color: @accentHover; }
QPushButton#primaryButton:focus, QPushButton#primaryButton:pressed {
    background-color: @accent;
    border: none;
    outline: none;
}
QLabel#fileBadge {
    color: @accent;
    background-color: @selection;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 600;
}
QToolTip {
    background-color: @sidebar;
    color: @text;
    border: 1px solid @border;
    padding: 5px;
}
"""


class Theme(QObject):
    changed = Signal()

    _instance: Theme | None = None

    def __init__(self) -> None:
        super().__init__()
        self._app: QApplication | None = None
        self._mode = ThemeMode.SYSTEM
        self._dark = False
        self._colors = colors_for(False)

    @classmethod
    def instance(cls) -> Theme:
        if cls._instance is None:
            cls._instance = Theme()
        return cls._instance

    def initialize(self, application: QApplication) -> None:
        self._app = application
        font = QFont()
        font.setFamilies(["Helvetica Neue", "Segoe UI", "Arial"])
        font.setPointSize(13)
        application.setFont(font)

        settings = QSettings(ORG, APP)
        raw = str(settings.value(THEME_KEY, "system") or "system")
        self._mode = ThemeMode(raw) if raw in {m.value for m in ThemeMode} else ThemeMode.SYSTEM

        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_system_scheme_changed)

        self.apply()

    def _on_system_scheme_changed(self, *_args) -> None:
        if self._mode is ThemeMode.SYSTEM:
            self.apply()

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    def is_dark(self) -> bool:
        return self._dark

    def text_color(self) -> QColor:
        return QColor(self._colors.text)

    def muted_text_color(self) -> QColor:
        return QColor(self._colors.muted_text)

    def accent_color(self) -> QColor:
        return QColor(self._colors.accent)

    def border_color(self) -> QColor:
        return QColor(self._colors.border)

    def set_mode(self, mode: ThemeMode) -> None:
        if self._mode is mode:
            return
        self._mode = mode
        QSettings(ORG, APP).setValue(THEME_KEY, mode.value)
        self.apply()

    def system_uses_dark(self) -> bool:
        hints = QGuiApplication.styleHints()
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
        return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def apply(self) -> None:
        if self._app is None:
            return
        self._dark = (
            self.system_uses_dark() if self._mode is ThemeMode.SYSTEM else self._mode is ThemeMode.DARK
        )
        self._colors = colors_for(self._dark)
        sheet = _STYLE
        for key, value in {
            "@background": self._colors.background,
            "@sidebar": self._colors.sidebar,
            "@selection": self._colors.selection,
            "@text": self._colors.text,
            "@mutedText": self._colors.muted_text,
            "@border": self._colors.border,
            "@accentText": self._colors.accent_text,
            "@accentHover": self._colors.accent_hover,
            "@accent": self._colors.accent,
        }.items():
            sheet = sheet.replace(key, value)
        self._app.setStyleSheet(sheet)

        palette = self._app.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self._colors.background))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(self._colors.text))
        palette.setColor(QPalette.ColorRole.Base, QColor(self._colors.background))
        palette.setColor(QPalette.ColorRole.Text, QColor(self._colors.text))
        palette.setColor(QPalette.ColorRole.Button, QColor(self._colors.sidebar))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(self._colors.text))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(self._colors.accent))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(self._colors.accent_text))
        self._app.setPalette(palette)
        self.changed.emit()

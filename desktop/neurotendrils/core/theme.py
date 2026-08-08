"""Application theme: palette, typography, and the global stylesheet.

Design constraints: flat surfaces, muted grayscale, a single accent color,
subtle separators instead of borders, and an 8px spacing system.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
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
    sidebar: str  # elevated surface (rail, inputs, quiet fills)
    selection: str  # hover / pressed wash
    text: str
    muted_text: str
    border: str  # hairline separator
    accent: str
    accent_hover: str
    accent_text: str
    error: str


def colors_for(dark: bool) -> ThemeColors:
    if dark:
        return ThemeColors(
            background="#0f1013",
            sidebar="#14161a",
            selection="#1c1f25",
            text="#e7e9ed",
            muted_text="#8f949e",
            border="#23262d",
            accent="#6f8dff",
            accent_hover="#89a1ff",
            accent_text="#0f1013",
            error="#ea6a6a",
        )
    return ThemeColors(
        background="#ffffff",
        sidebar="#fafafb",
        selection="#f1f2f4",
        text="#16181d",
        muted_text="#6b7280",
        border="#e8e9ec",
        accent="#2f6feb",
        accent_hover="#2559c8",
        accent_text="#ffffff",
        error="#c8443c",
    )


_STYLE = """
/* ---------- shell ---------- */
QMainWindow, QWidget#appRoot {
    background-color: @background;
    color: @text;
}
QStackedWidget#pageStack { background: transparent; }

/* ---------- left navigation ---------- */
QWidget#navRail {
    background-color: @sidebar;
    border: none;
}
QFrame#shellDivider {
    background-color: @border;
    border: none;
    max-width: 1px;
    min-width: 1px;
}
QLabel#navBrand {
    color: @text;
    font-size: 13px;
    font-weight: 700;
}
QLabel#navBrandMark {
    background: transparent;
    border: none;
}
QLabel#navSectionLabel {
    color: @mutedText;
    font-size: 10px;
    font-weight: 700;
}
QToolButton#navItem {
    background: transparent;
    border: none;
    outline: none;
    color: @mutedText;
    font-size: 13px;
    font-weight: 500;
    padding: 0 8px;
    text-align: left;
}
QToolButton#navItem:hover { color: @text; }
QToolButton#navItem:checked {
    color: @text;
    font-weight: 700;
}
QToolButton#navToggle {
    background: transparent;
    border: none;
    outline: none;
    color: @mutedText;
    font-size: 12px;
    font-weight: 500;
    padding: 0 8px;
    text-align: left;
}
QToolButton#navToggle:hover { color: @text; }

/* ---------- top bar ---------- */
QWidget#topBar {
    background-color: @background;
    border-bottom: 1px solid @border;
}
QLabel#topBarTitle {
    color: @text;
    font-size: 13px;
    font-weight: 600;
}
QToolButton#projectSwitcher {
    color: @text;
    font-size: 13px;
    font-weight: 600;
    border: none;
    background: transparent;
    padding: 4px 2px;
}
QToolButton#projectSwitcher:hover { color: @mutedText; }
QToolButton#projectSwitcher::menu-indicator { image: none; width: 0; }
QWidget#stageToolbar { background: transparent; }
/* Top-bar search: chrome on the shell; the line edit stays borderless so
   macOS QSS padding does not clip glyph ascenders. */
QFrame#searchShell {
    background-color: @sidebar;
    border: 1px solid @border;
    border-radius: 8px;
}
QFrame#searchShell[focused="true"] { border: 1px solid @accent; }
QLineEdit#searchInput {
    background: transparent;
    color: @text;
    border: none;
    border-radius: 0;
    padding: 0;
    margin: 0;
    min-height: 0;
    font-size: 13px;
    selection-background-color: @accent;
    selection-color: @accentText;
}
QLineEdit#searchInput:focus { border: none; outline: none; }
QLabel#searchHint {
    color: @mutedText;
    font-size: 11px;
    font-weight: 500;
    padding: 0 2px;
}
QToolButton#iconButton {
    background: transparent;
    border: none;
    outline: none;
    padding: 0;
}
QToolButton#iconButton:hover { background-color: @selection; border-radius: 6px; }
QToolButton#avatarButton {
    background: transparent;
    border: none;
    outline: none;
    padding: 0;
}

/* ---------- page scaffolding ---------- */
QScrollArea#pageScroll { background: transparent; border: none; }
QWidget#pageContent { background: transparent; }
QLabel#pageTitle {
    color: @text;
    font-size: 20px;
    font-weight: 600;
}
QLabel#pageDescription {
    color: @mutedText;
    font-size: 13px;
    line-height: 1.4;
    padding-right: 8px;
}
QLabel#sectionLabel, QLabel#groupLabel {
    color: @mutedText;
    font-size: 10px;
    font-weight: 700;
}
QFrame#separator {
    background-color: @border;
    border: none;
    max-height: 1px;
    min-height: 1px;
}
QFrame#statDivider {
    background-color: @border;
    border: none;
    max-width: 1px;
    min-width: 1px;
}

/* ---------- list rows ---------- */
QWidget#listRow { background: transparent; border: none; border-radius: 6px; }
QWidget#listRow:hover { background-color: @selection; border-radius: 6px; }
QWidget#listRowSelected { background-color: @selection; border-radius: 6px; }
QLabel#rowTitle {
    color: @text;
    font-size: 13px;
    font-weight: 500;
}
QLabel#rowTitleSelected {
    color: @text;
    font-size: 13px;
    font-weight: 700;
}
QLabel#rowSubtitle, QLabel#rowMeta {
    color: @mutedText;
    font-size: 12px;
}
QLabel#rowMono {
    color: @mutedText;
    font-size: 11px;
    font-family: @mono;
}
QLabel#statValue {
    color: @text;
    font-size: 18px;
    font-weight: 600;
}
QLabel#statLabel {
    color: @mutedText;
    font-size: 11px;
    font-weight: 500;
}

/* ---------- staged workspace (quiet, text-first) ---------- */
QWidget#stageChip { background: transparent; border: none; }
QLabel#stageIndex, QLabel#stageIndexCurrent, QLabel#stageIndexLocked,
QLabel#stageIndexDone {
    background: transparent;
    border: none;
    font-size: 11px;
    font-weight: 600;
}
QLabel#stageIndex { color: @mutedText; }
QLabel#stageIndexCurrent { color: @text; }
QLabel#stageIndexLocked { color: @mutedText; }
QLabel#stageIndexDone { color: @accent; }
QLabel#stageLabel, QLabel#stageLabelCurrent, QLabel#stageLabelLocked {
    font-size: 13px;
}
QLabel#stageLabel { color: @mutedText; font-weight: 500; }
QLabel#stageLabelCurrent { color: @text; font-weight: 600; }
QLabel#stageLabelLocked { color: @mutedText; font-weight: 500; }
QWidget#stageChip:hover QLabel#stageLabel { color: @text; }
QFrame#stageConnector, QFrame#stageConnectorDone {
    background-color: @border;
    border: none;
}
QFrame#stageIndicator {
    background-color: @accent;
    border: none;
    border-radius: 1px;
}
QWidget#stageFooter { background-color: @background; }
QLabel#stageStatus {
    color: @mutedText;
    font-size: 12px;
}
QWidget#contextStrip { background: transparent; }
QLabel#contextKey { color: @mutedText; font-size: 10px; font-weight: 700; }
QLabel#contextValue {
    color: @text;
    font-size: 12px;
    font-weight: 500;
}
QWidget#trainChart {
    background: transparent;
    border: none;
}

/* ---------- project grid ---------- */
QFrame#projectCard {
    background-color: @sidebar;
    border: 1px solid @border;
    border-radius: 10px;
}
QFrame#projectCard:hover { border-color: @mutedText; }
QLabel#projectCardTitle {
    color: @text;
    font-size: 15px;
    font-weight: 600;
}
QLabel#projectCardMeta, QLabel#projectCardAge {
    color: @mutedText;
    font-size: 12px;
}

/* ---------- notifications / search popovers ---------- */
/* Borders are painted in code — QSS border-radius leaves a gap on one edge. */
QFrame#notificationPanel, QFrame#searchPopup {
    background: transparent;
    border: none;
}
QWidget#notificationChrome { background: transparent; }
QLabel#notificationTitle {
    color: @text;
    font-size: 13px;
    font-weight: 700;
}
QFrame#notificationRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid @border;
}
QFrame#notificationRowLast {
    background: transparent;
    border: none;
}
QLabel#notificationRowTitle {
    color: @text;
    font-size: 12px;
    font-weight: 600;
}
QLabel#notificationRowBody {
    color: @mutedText;
    font-size: 12px;
}
QLabel#notificationBadge {
    color: @accentText;
    background-color: @accent;
    border-radius: 7px;
    font-size: 10px;
    font-weight: 700;
    padding: 0 4px;
    min-width: 14px;
}
QMenu#projectMenu {
    background-color: @background;
    border: 1px solid @border;
    border-radius: 8px;
    padding: 4px;
}
QMenu#projectMenu::item {
    color: @text;
    padding: 6px 12px;
    border-radius: 4px;
}
QMenu#projectMenu::item:selected {
    background-color: @selection;
}
QMenu#projectMenu::separator {
    height: 1px;
    background: @border;
    margin: 4px 8px;
}
QLabel#searchPopupHeader {
    color: @mutedText;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    border-bottom: 1px solid @border;
}
QFrame#searchHitRow {
    background: transparent;
    border: none;
    border-radius: 6px;
}
QFrame#searchHitRow:hover { background-color: @selection; }
QLabel#searchHitTitle {
    color: @text;
    font-size: 12px;
    font-weight: 600;
}
QLabel#searchHitMeta {
    color: @mutedText;
    font-size: 11px;
}
QLabel#searchHitKind {
    color: @mutedText;
    font-size: 10px;
    font-weight: 600;
}

/* ---------- inspector ---------- */
QWidget#inspector {
    background-color: @background;
    border-left: 1px solid @border;
}
QLabel#inspectorTitle {
    color: @text;
    font-size: 14px;
    font-weight: 600;
}
QLabel#inspectorKey {
    color: @mutedText;
    font-size: 11px;
    font-weight: 500;
}
QLabel#inspectorValue {
    color: @text;
    font-size: 12px;
    padding-top: 1px;
    line-height: 1.35;
}
QWidget#inspector QPushButton#ghostButton {
    text-align: left;
    padding: 6px 8px;
}

/* ---------- buttons ---------- */
QPushButton#primaryButton {
    background-color: @accent;
    color: @accentText;
    border: none;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    min-width: 0;
    outline: none;
}
QPushButton#primaryButton:hover { background-color: @accentHover; }
QPushButton#primaryButton:pressed, QPushButton#primaryButton:focus {
    background-color: @accent;
    border: none;
    outline: none;
}
QPushButton#primaryButton:disabled {
    background-color: @selection;
    color: @mutedText;
}
QPushButton#secondaryButton, QPushButton#planStepButton {
    background: transparent;
    color: @text;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
    outline: none;
}
QPushButton#secondaryButton:hover, QPushButton#planStepButton:hover {
    background-color: @selection;
}
QPushButton#secondaryButton:pressed, QPushButton#secondaryButton:focus,
QPushButton#planStepButton:pressed, QPushButton#planStepButton:focus {
    background: transparent;
    border: 1px solid @border;
    outline: none;
}
QPushButton#secondaryButton:disabled, QPushButton#planStepButton:disabled {
    color: @mutedText;
    border-color: @border;
}
QPushButton#planStepButton {
    padding: 3px 8px;
    font-size: 11px;
    min-width: 0;
    min-height: 0;
}
QPushButton#ghostButton {
    background: transparent;
    color: @mutedText;
    border: none;
    border-radius: 6px;
    padding: 4px 6px;
    font-size: 12px;
    font-weight: 600;
    outline: none;
}
QPushButton#ghostButton:hover { color: @text; }
QPushButton#ghostButton:disabled { color: @mutedText; }

/* ---------- inputs ---------- */
QDoubleSpinBox, QSpinBox, QLineEdit {
    background-color: @sidebar;
    color: @text;
    border: 1px solid @border;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 12px;
    min-height: 18px;
    selection-background-color: @accent;
    selection-color: @accentText;
}
QDoubleSpinBox:focus, QSpinBox:focus, QLineEdit:focus {
    border: 1px solid @accent;
    outline: none;
}
/* Project-grid search and other plain search fields. */
QLineEdit#searchField {
    background-color: @sidebar;
    color: @text;
    border: 1px solid @border;
    border-radius: 8px;
    padding: 0 28px 0 12px;
    min-height: 0;
    font-size: 13px;
    selection-background-color: @accent;
    selection-color: @accentText;
}
QLineEdit#searchField:focus { border: 1px solid @accent; outline: none; }
/* Combos stay closer to the platform control so Studio feels native. */
QComboBox {
    color: @text;
    font-size: 12px;
    min-height: 22px;
    padding: 2px 6px;
}
QCheckBox { color: @text; font-size: 12px; spacing: 8px; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid @border;
    border-radius: 4px;
    background-color: @background;
}
QCheckBox::indicator:hover { border-color: @mutedText; }
QCheckBox::indicator:checked {
    background-color: @accent;
    border-color: @accent;
}

/* ---------- panels used by module pages ---------- */
QFrame#emptyPanel {
    background: transparent;
    border: 1px dashed @border;
    border-radius: 8px;
}
QFrame#filePanel, QFrame#fingerprintPanel,
QFrame#libraryPanel, QFrame#detailPanel {
    background-color: @sidebar;
    border: 1px solid @border;
    border-radius: 8px;
}
QLabel#emptyPanelTitle { color: @text; font-size: 13px; font-weight: 600; }
QLabel#emptyPanelHint { color: @mutedText; font-size: 12px; }
QLabel#fileNameLabel { color: @text; font-size: 13px; font-weight: 600; }
QLabel#fileMetaLabel { color: @mutedText; font-size: 12px; }
QLabel#filePathLabel {
    color: @mutedText;
    font-size: 11px;
    font-family: @mono;
}
QLabel#fingerprintKey { color: @mutedText; font-size: 11px; }
QLabel#fingerprintValue {
    color: @text;
    font-size: 13px;
    font-weight: 600;
    padding-top: 1px;
}
QLabel#fingerprintChannels {
    color: @mutedText;
    font-size: 12px;
    padding-top: 2px;
    line-height: 1.35;
}
QFrame#planStepRow, QFrame#templateRow, QFrame#templateRowSelected,
QFrame#libraryRow {
    background: transparent;
    border: none;
    border-bottom: 1px solid @border;
    border-radius: 0;
}
QFrame#planStepRow:hover, QFrame#templateRow:hover {
    background-color: @selection;
}
QFrame#templateRowSelected {
    background-color: @selection;
    border-left: 2px solid @accent;
}
QLabel#planStepIndex {
    color: @mutedText;
    background-color: @selection;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#planStepTitle, QLabel#templateTitle, QLabel#templateTitleSelected {
    color: @text;
    font-size: 13px;
    font-weight: 500;
}
QLabel#templateTitleSelected { font-weight: 700; }
QLabel#planStepMeta, QLabel#templateMeta {
    color: @mutedText;
    font-size: 11px;
    font-family: @mono;
}
QLabel#planStepRationale, QLabel#templateRationale {
    color: @mutedText;
    font-size: 11px;
}
QLabel#stepEditError { color: @error; font-size: 12px; }
QLabel#fileBadge {
    color: @mutedText;
    background: transparent;
    border: 1px solid @border;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    font-weight: 700;
}

/* ---------- storage meter ---------- */
QProgressBar#storageBar {
    background-color: @selection;
    border: none;
    border-radius: 2px;
}
QProgressBar#storageBar::chunk {
    background-color: @accent;
    border-radius: 2px;
}
QLabel#userName { color: @text; font-size: 12px; font-weight: 600; }
QLabel#userStorage { color: @mutedText; font-size: 11px; }

/* ---------- modals ---------- */
QWidget#modalHost { background-color: rgba(9, 10, 13, 165); }
QFrame#modalPanel {
    background-color: @background;
    border: 1px solid @border;
    border-radius: 10px;
}
QWidget#settingsPanel, QWidget#schemaEditPanel, QWidget#modalMessagePanel {
    background: transparent;
    border: none;
}
QLabel#modalTitle { color: @text; font-size: 15px; font-weight: 600; }
QLabel#modalBody { color: @mutedText; font-size: 12px; }
QListWidget#modalChoiceList {
    background: transparent;
    border: 1px solid @border;
    border-radius: 6px;
    outline: none;
    padding: 4px;
}
QListWidget#modalChoiceList::item {
    color: @mutedText;
    border: none;
    border-radius: 4px;
    padding: 6px 8px;
}
QListWidget#modalChoiceList::item:selected,
QListWidget#modalChoiceList::item:hover {
    background: transparent;
    color: @text;
    font-weight: 700;
}

/* ---------- settings ---------- */
QWidget#settingsSidebar {
    background-color: @sidebar;
    border-right: 1px solid @border;
}
QLabel#settingsNavTitle { color: @mutedText; font-size: 10px; font-weight: 700; }
QListWidget#settingsNav {
    background: transparent;
    border: none;
    outline: none;
    font-size: 13px;
}
QListWidget#settingsNav::item {
    background: transparent;
    color: @mutedText;
    border: none;
    padding: 6px 8px;
}
QListWidget#settingsNav::item:hover { color: @text; }
QListWidget#settingsNav::item:selected {
    background: transparent;
    color: @text;
    font-weight: 700;
}
QLabel#settingTitle { color: @text; font-size: 13px; font-weight: 600; }
QLabel#settingDescription { color: @mutedText; font-size: 12px; }

/* ---------- scrollbars ---------- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: @border;
    border-radius: 5px;
    min-height: 32px;
}
QScrollBar::handle:vertical:hover { background-color: @mutedText; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal {
    background-color: @border;
    border-radius: 5px;
    min-width: 32px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

QToolTip {
    background-color: @background;
    color: @text;
    border: 1px solid @border;
    padding: 4px 6px;
}
"""


_FONT_CANDIDATES = ("Inter", "SF Pro Text", "Helvetica Neue", "Segoe UI", "Arial")
_MONO_CANDIDATES = ("SF Mono", "Menlo", "JetBrains Mono", "Consolas", "DejaVu Sans Mono")


def _installed_families(candidates: tuple[str, ...]) -> list[str]:
    installed = set(QFontDatabase.families())
    return [name for name in candidates if name in installed]


def _ui_font() -> QFont:
    """Prefer a neutral UI face, but never request a family Qt cannot resolve."""
    font = QFont()
    available = _installed_families(_FONT_CANDIDATES)
    if available:
        font.setFamilies(available)
    font.setPointSize(13)
    return font


def _mono_family() -> str:
    available = _installed_families(_MONO_CANDIDATES)
    return f'"{available[0]}", monospace' if available else "monospace"


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
        application.setFont(_ui_font())

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

    def colors(self) -> ThemeColors:
        return self._colors

    def text_color(self) -> QColor:
        return QColor(self._colors.text)

    def muted_text_color(self) -> QColor:
        return QColor(self._colors.muted_text)

    def accent_color(self) -> QColor:
        return QColor(self._colors.accent)

    def border_color(self) -> QColor:
        return QColor(self._colors.border)

    def surface_color(self) -> QColor:
        return QColor(self._colors.sidebar)

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

        hints = QGuiApplication.styleHints()
        # Drive the native title bar / window chrome (macOS, Windows 11) so it
        # matches the in-app theme instead of staying stuck on the OS light bar.
        if self._mode is ThemeMode.SYSTEM:
            if hasattr(hints, "setColorScheme"):
                hints.setColorScheme(Qt.ColorScheme.Unknown)
            self._dark = self.system_uses_dark()
        else:
            self._dark = self._mode is ThemeMode.DARK
            if hasattr(hints, "setColorScheme"):
                hints.setColorScheme(
                    Qt.ColorScheme.Dark if self._dark else Qt.ColorScheme.Light
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
            "@error": self._colors.error,
            "@mono": _mono_family(),
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

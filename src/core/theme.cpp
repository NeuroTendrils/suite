#include "core/theme.hpp"

#include <QApplication>
#include <QColor>
#include <QFont>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QSettings>
#include <QStyleHints>
#include <QtGlobal>

namespace
{
constexpr auto themeSettingKey = "appearance/theme";

struct ThemeColors
{
    QColor background;
    QColor sidebar;
    QColor selection;
    QColor text;
    QColor mutedText;
    QColor border;
    QColor accent;
    QColor accentHover;
    QColor accentText;
    QColor error;
};

ThemeColors colorsFor(bool dark)
{
    if (dark) {
        return {
            QColor(QStringLiteral("#0b0d13")),
            QColor(QStringLiteral("#10131a")),
            QColor(QStringLiteral("#20242e")),
            QColor(QStringLiteral("#e8eaf1")),
            QColor(QStringLiteral("#9ca3b5")),
            QColor(QStringLiteral("#252a36")),
            QColor(QStringLiteral("#7795f8")),
            QColor(QStringLiteral("#8ca6ff")),
            QColor(QStringLiteral("#0b0d13")),
            QColor(QStringLiteral("#f06a78")),
        };
    }

    return {
        QColor(QStringLiteral("#ffffff")),
        QColor(QStringLiteral("#f7f8fa")),
        QColor(QStringLiteral("#eceef1")),
        QColor(QStringLiteral("#1b1f35")),
        QColor(QStringLiteral("#687086")),
        QColor(QStringLiteral("#e2e5eb")),
        QColor(QStringLiteral("#3758bc")),
        QColor(QStringLiteral("#2f4fac")),
        QColor(QStringLiteral("#ffffff")),
        QColor(QStringLiteral("#c83f52")),
    };
}

QString modeToString(ThemeMode mode)
{
    switch (mode) {
    case ThemeMode::Light:
        return QStringLiteral("light");
    case ThemeMode::Dark:
        return QStringLiteral("dark");
    case ThemeMode::System:
        return QStringLiteral("system");
    }

    return QStringLiteral("system");
}

ThemeMode modeFromString(const QString &value)
{
    if (value == QStringLiteral("light")) {
        return ThemeMode::Light;
    }
    if (value == QStringLiteral("dark")) {
        return ThemeMode::Dark;
    }
    return ThemeMode::System;
}

QString buildStyleSheet(const ThemeColors &colors)
{
    QString styleSheet = QStringLiteral(R"(
        QMainWindow, QWidget#appRoot {
            background-color: @background;
            color: @text;
        }

        QWidget#sidebar {
            background-color: @sidebar;
            border-right: 1px solid @border;
        }

        QLabel#brandNeuro, QLabel#brandTendrils {
            font-size: 17px;
            font-weight: 700;
        }

        QLabel#brandNeuro {
            color: @accent;
        }

        QLabel#brandTendrils {
            color: @text;
        }

        QListWidget#moduleNavigation {
            background: transparent;
            border: none;
            outline: none;
            font-size: 13px;
        }

        QListWidget#moduleNavigation::item {
            color: @mutedText;
            border: none;
            border-radius: 6px;
            margin: 2px 0;
            padding: 9px 10px;
        }

        QListWidget#moduleNavigation::item:hover {
            background-color: @selection;
            color: @text;
        }

        QListWidget#moduleNavigation::item:selected {
            background-color: @selection;
            color: @text;
            font-weight: 600;
        }

        QWidget#userCard {
            border-top: 1px solid @border;
        }

        QLabel#userName {
            color: @text;
            font-size: 13px;
            font-weight: 600;
        }

        QLabel#userStorage {
            color: @mutedText;
            font-size: 11px;
        }

        QProgressBar#storageBar {
            background-color: @selection;
            border: none;
            border-radius: 2px;
        }

        QProgressBar#storageBar::chunk {
            background-color: @accent;
            border-radius: 2px;
        }

        QToolButton#settingsButton {
            background: transparent;
            border: none;
            border-radius: 5px;
            padding: 5px;
        }

        QToolButton#settingsButton:hover {
            background-color: @selection;
        }

        QLabel#pageTitle {
            color: @text;
            font-size: 22px;
            font-weight: 700;
        }

        QLabel#pageDescription {
            color: @mutedText;
            font-size: 13px;
        }

        QWidget#settingsSidebar {
            background-color: @sidebar;
            border-right: 1px solid @border;
        }

        QLabel#settingsNavTitle {
            color: @mutedText;
            font-size: 15px;
            font-weight: 600;
        }

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

        QListWidget#settingsNav::item:hover {
            color: @text;
        }

        QListWidget#settingsNav::item:selected {
            background: transparent;
            color: @text;
            font-weight: 600;
        }

        QLabel#groupLabel {
            color: @text;
            font-size: 15px;
            font-weight: 500;
        }

        QLabel#settingTitle {
            color: @text;
            font-size: 13px;
            font-weight: 600;
        }

        QLabel#settingDescription {
            color: @mutedText;
            font-size: 12px;
        }

        QPlainTextEdit#diagnosticsLog {
            background-color: @sidebar;
            color: @text;
            border: 1px solid @border;
            border-radius: 6px;
            font-family: Menlo, Monaco, Consolas, monospace;
            font-size: 11px;
            padding: 8px;
        }

        QScrollArea#pageScroll {
            background: transparent;
            border: none;
        }

        QWidget#pageContent {
            background: transparent;
        }

        QFrame#emptyPanel {
            background-color: @sidebar;
            border: 1px dashed @border;
            border-radius: 10px;
        }

        QFrame#filePanel, QFrame#fingerprintPanel, QFrame#upcomingPanel {
            background-color: @sidebar;
            border: 1px solid @border;
            border-radius: 10px;
        }

        QLabel#emptyPanelTitle {
            color: @text;
            font-size: 15px;
            font-weight: 600;
        }

        QLabel#emptyPanelHint {
            color: @mutedText;
            font-size: 12px;
        }

        QLabel#fileNameLabel {
            color: @text;
            font-size: 14px;
            font-weight: 600;
        }

        QLabel#fileMetaLabel {
            color: @mutedText;
            font-size: 12px;
        }

        QLabel#filePathLabel {
            color: @mutedText;
            font-size: 11px;
            font-family: Menlo, Monaco, Consolas, monospace;
        }

        QLabel#upcomingCaption {
            color: @mutedText;
            font-size: 12px;
        }

        QLabel#fingerprintKey {
            color: @mutedText;
            font-size: 11px;
        }

        QLabel#fingerprintValue {
            color: @text;
            font-size: 13px;
            font-weight: 600;
        }

        QLabel#fingerprintChannels {
            color: @mutedText;
            font-size: 12px;
        }

        QFrame#planStepRow {
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

        QLabel#planStepTitle {
            color: @text;
            font-size: 13px;
            font-weight: 600;
        }

        QLabel#planStepMeta {
            color: @mutedText;
            font-size: 11px;
            font-family: Menlo, Monaco, Consolas, monospace;
        }

        QLabel#planStepRationale {
            color: @mutedText;
            font-size: 11px;
        }

        QLabel#stepEditError {
            color: #c45c5c;
            font-size: 12px;
        }

        QPushButton#primaryButton {
            background-color: @accent;
            color: @accentText;
            border: none;
            border-radius: 7px;
            padding: 8px 14px;
            font-size: 13px;
            font-weight: 600;
            min-width: 110px;
        }

        QPushButton#primaryButton:hover {
            background-color: @accentHover;
        }

        QPushButton#primaryButton:pressed {
            padding-top: 10px;
            padding-bottom: 8px;
        }

        QPushButton#secondaryButton {
            background: transparent;
            color: @text;
            border: 1px solid @border;
            border-radius: 7px;
            padding: 6px 12px;
            font-size: 12px;
        }

        QPushButton#secondaryButton:hover {
            background-color: @selection;
        }

        QPushButton#secondaryButton:disabled {
            color: @mutedText;
            border-color: @border;
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
    )");

    styleSheet.replace(QStringLiteral("@background"), colors.background.name());
    styleSheet.replace(QStringLiteral("@sidebar"), colors.sidebar.name());
    styleSheet.replace(QStringLiteral("@selection"), colors.selection.name());
    styleSheet.replace(QStringLiteral("@text"), colors.text.name());
    styleSheet.replace(QStringLiteral("@mutedText"), colors.mutedText.name());
    styleSheet.replace(QStringLiteral("@border"), colors.border.name());
    styleSheet.replace(QStringLiteral("@accentText"), colors.accentText.name());
    styleSheet.replace(QStringLiteral("@accentHover"), colors.accentHover.name());
    styleSheet.replace(QStringLiteral("@accent"), colors.accent.name());
    return styleSheet;
}
}

Theme &Theme::instance()
{
    static Theme theme;
    return theme;
}

Theme::Theme() = default;

void Theme::initialize(QApplication &application)
{
    application_ = &application;
    systemPalette_ = application.palette();

    for (const auto &fontFile : {QStringLiteral(":/fonts/Inter-Regular.ttf"),
                                 QStringLiteral(":/fonts/Inter-Medium.ttf"),
                                 QStringLiteral(":/fonts/Inter-SemiBold.ttf"),
                                 QStringLiteral(":/fonts/Inter-Bold.ttf")}) {
        QFontDatabase::addApplicationFont(fontFile);
    }
    QFont appFont(QStringLiteral("Inter"));
    appFont.setPointSize(13);
    application.setFont(appFont);

    const QSettings settings;
    mode_ = modeFromString(settings.value(themeSettingKey, QStringLiteral("system")).toString());

#if QT_VERSION >= QT_VERSION_CHECK(6, 5, 0)
    connect(QGuiApplication::styleHints(),
            &QStyleHints::colorSchemeChanged,
            this,
            [this](Qt::ColorScheme) {
                if (mode_ == ThemeMode::System && !applying_) {
                    apply();
                }
            });
#endif

    apply();
}

ThemeMode Theme::mode() const
{
    return mode_;
}

bool Theme::isDark() const
{
    return dark_;
}

QColor Theme::accentColor() const
{
    return accent_;
}

QColor Theme::textColor() const
{
    return text_;
}

QColor Theme::mutedTextColor() const
{
    return mutedText_;
}

QColor Theme::borderColor() const
{
    return border_;
}

void Theme::setMode(ThemeMode mode)
{
    if (mode_ == mode) {
        return;
    }

    mode_ = mode;
    QSettings settings;
    settings.setValue(themeSettingKey, modeToString(mode_));
    apply();
    emit modeChanged(mode_);
}

bool Theme::systemUsesDarkColors() const
{
#if QT_VERSION >= QT_VERSION_CHECK(6, 5, 0)
    const auto colorScheme = QGuiApplication::styleHints()->colorScheme();
    if (colorScheme != Qt::ColorScheme::Unknown) {
        return colorScheme == Qt::ColorScheme::Dark;
    }
#endif

    return systemPalette_.color(QPalette::Window).lightness() < 128;
}

void Theme::apply()
{
    if (application_ == nullptr || applying_) {
        return;
    }

    applying_ = true;

#if QT_VERSION >= QT_VERSION_CHECK(6, 8, 0)
    auto *styleHints = QGuiApplication::styleHints();
    switch (mode_) {
    case ThemeMode::System:
        styleHints->unsetColorScheme();
        break;
    case ThemeMode::Light:
        styleHints->setColorScheme(Qt::ColorScheme::Light);
        break;
    case ThemeMode::Dark:
        styleHints->setColorScheme(Qt::ColorScheme::Dark);
        break;
    }
#endif

    const bool dark = mode_ == ThemeMode::Dark
                      || (mode_ == ThemeMode::System && systemUsesDarkColors());
    const ThemeColors colors = colorsFor(dark);

    dark_ = dark;
    accent_ = colors.accent;
    text_ = colors.text;
    mutedText_ = colors.mutedText;
    border_ = colors.border;

    QPalette palette = systemPalette_;
    palette.setColor(QPalette::Window, colors.background);
    palette.setColor(QPalette::WindowText, colors.text);
    palette.setColor(QPalette::Base, colors.sidebar);
    palette.setColor(QPalette::AlternateBase, colors.selection);
    palette.setColor(QPalette::ToolTipBase, colors.sidebar);
    palette.setColor(QPalette::ToolTipText, colors.text);
    palette.setColor(QPalette::Text, colors.text);
    palette.setColor(QPalette::Button, colors.sidebar);
    palette.setColor(QPalette::ButtonText, colors.text);
    palette.setColor(QPalette::BrightText, colors.error);
    palette.setColor(QPalette::Link, colors.accent);
    palette.setColor(QPalette::Highlight, colors.accent);
    palette.setColor(QPalette::HighlightedText, colors.accentText);
    palette.setColor(QPalette::PlaceholderText, colors.mutedText);
    palette.setColor(QPalette::Disabled, QPalette::WindowText, colors.mutedText);
    palette.setColor(QPalette::Disabled, QPalette::Text, colors.mutedText);
    palette.setColor(QPalette::Disabled, QPalette::ButtonText, colors.mutedText);

    application_->setPalette(palette);
    application_->setStyleSheet(buildStyleSheet(colors));
    applying_ = false;

    emit changed();
}

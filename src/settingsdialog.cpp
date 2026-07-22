#include "settingsdialog.hpp"

#include "core/theme.hpp"
#include "widgets/themepreviewcard.hpp"

#include <QApplication>
#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QPushButton>
#include <QStackedWidget>
#include <QVBoxLayout>

SettingsDialog::SettingsDialog(QWidget *parent)
    : QDialog(parent)
    , nav_(new QListWidget(this))
    , panes_(new QStackedWidget(this))
{
    setWindowTitle(tr("Settings"));
    // Window-modal so it presents as a native sheet on macOS instead of
    // a detached popup window.
    setWindowModality(Qt::WindowModal);
    resize(680, 440);

    auto *layout = new QHBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    auto *sidebar = new QWidget(this);
    sidebar->setObjectName(QStringLiteral("settingsSidebar"));
    sidebar->setFixedWidth(172);
    auto *sidebarLayout = new QVBoxLayout(sidebar);
    sidebarLayout->setContentsMargins(16, 22, 12, 12);
    sidebarLayout->setSpacing(12);

    auto *navTitle = new QLabel(tr("Settings"), sidebar);
    navTitle->setObjectName(QStringLiteral("settingsNavTitle"));

    nav_->setObjectName(QStringLiteral("settingsNav"));
    nav_->setAccessibleName(tr("Settings sections"));
    nav_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    nav_->addItem(tr("Appearance"));
    nav_->addItem(tr("Info"));

    sidebarLayout->addWidget(navTitle);
    sidebarLayout->addWidget(nav_, 1);

    panes_->addWidget(createAppearancePane());
    panes_->addWidget(createInfoPane());

    auto *content = new QWidget(this);
    auto *contentLayout = new QVBoxLayout(content);
    contentLayout->setContentsMargins(0, 0, 0, 0);
    contentLayout->setSpacing(0);

    auto *doneButton = new QPushButton(tr("Done"), content);
    doneButton->setDefault(true);
    connect(doneButton, &QPushButton::clicked, this, &QDialog::accept);

    auto *buttonRow = new QWidget(content);
    auto *buttonRowLayout = new QHBoxLayout(buttonRow);
    buttonRowLayout->setContentsMargins(16, 0, 16, 14);
    buttonRowLayout->addStretch();
    buttonRowLayout->addWidget(doneButton);

    contentLayout->addWidget(panes_, 1);
    contentLayout->addWidget(buttonRow);

    layout->addWidget(sidebar);
    layout->addWidget(content, 1);

    connect(nav_, &QListWidget::currentRowChanged, panes_, &QStackedWidget::setCurrentIndex);
    nav_->setCurrentRow(0);

    connect(&Theme::instance(), &Theme::modeChanged, this, [this](ThemeMode) { syncCards(); });
    syncCards();
}

QWidget *SettingsDialog::createAppearancePane()
{
    auto *pane = new QWidget(this);
    auto *layout = new QVBoxLayout(pane);
    layout->setContentsMargins(32, 28, 32, 24);
    layout->setSpacing(0);

    auto *title = new QLabel(tr("Appearance"), pane);
    title->setObjectName(QStringLiteral("pageTitle"));

    auto *themeLabel = new QLabel(tr("Theme"), pane);
    themeLabel->setObjectName(QStringLiteral("groupLabel"));

    lightCard_ = new ThemePreviewCard(ThemePreviewCard::Preview::Light, tr("Light"), pane);
    darkCard_ = new ThemePreviewCard(ThemePreviewCard::Preview::Dark, tr("Dark"), pane);
    autoCard_ = new ThemePreviewCard(ThemePreviewCard::Preview::Auto, tr("Auto"), pane);

    auto *cards = new QWidget(pane);
    auto *cardsLayout = new QHBoxLayout(cards);
    cardsLayout->setContentsMargins(0, 0, 0, 0);
    cardsLayout->setSpacing(14);
    cardsLayout->addWidget(lightCard_);
    cardsLayout->addWidget(darkCard_);
    cardsLayout->addWidget(autoCard_);
    cardsLayout->addStretch();

    layout->addWidget(title);
    layout->addSpacing(20);
    layout->addWidget(themeLabel);
    layout->addSpacing(10);
    layout->addWidget(cards);
    layout->addStretch();

    const auto select = [](ThemeMode mode) {
        return [mode](bool checked) {
            if (checked) {
                Theme::instance().setMode(mode);
            }
        };
    };
    connect(lightCard_, &QAbstractButton::clicked, this, select(ThemeMode::Light));
    connect(darkCard_, &QAbstractButton::clicked, this, select(ThemeMode::Dark));
    connect(autoCard_, &QAbstractButton::clicked, this, select(ThemeMode::System));

    return pane;
}

QWidget *SettingsDialog::createInfoPane()
{
    auto *pane = new QWidget(this);
    auto *layout = new QVBoxLayout(pane);
    layout->setContentsMargins(32, 28, 32, 24);
    layout->setSpacing(0);

    auto *title = new QLabel(tr("Info"), pane);
    title->setObjectName(QStringLiteral("pageTitle"));

    auto *name = new QLabel(tr("NeuroTendrils"), pane);
    name->setObjectName(QStringLiteral("settingTitle"));

    auto *version =
        new QLabel(tr("Version %1").arg(QApplication::applicationVersion()), pane);
    version->setObjectName(QStringLiteral("settingDescription"));

    auto *description = new QLabel(
        tr("A local suite for EEG preprocessing, model training, and learning."), pane);
    description->setObjectName(QStringLiteral("settingDescription"));
    description->setWordWrap(true);

    layout->addWidget(title);
    layout->addSpacing(20);
    layout->addWidget(name);
    layout->addSpacing(4);
    layout->addWidget(version);
    layout->addSpacing(2);
    layout->addWidget(description);
    layout->addStretch();

    return pane;
}

void SettingsDialog::syncCards()
{
    const ThemeMode mode = Theme::instance().mode();
    lightCard_->setChecked(mode == ThemeMode::Light);
    darkCard_->setChecked(mode == ThemeMode::Dark);
    autoCard_->setChecked(mode == ThemeMode::System);
}

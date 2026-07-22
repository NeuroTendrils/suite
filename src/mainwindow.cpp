#include "mainwindow.hpp"

#include "core/theme.hpp"
#include "modules/hub/hubpage.hpp"
#include "modules/neuroflow/neuroflowpage.hpp"
#include "modules/neurolearn/neurolearnpage.hpp"
#include "modules/neurostudio/neurostudiopage.hpp"
#include "settingsdialog.hpp"
#include "widgets/icons.hpp"

#include <QHBoxLayout>
#include <QLabel>
#include <QListWidget>
#include <QProgressBar>
#include <QStackedWidget>
#include <QToolButton>
#include <QVBoxLayout>
#include <QWidget>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , navigation_(new QListWidget(this))
    , avatarLabel_(new QLabel(this))
    , settingsButton_(new QToolButton(this))
    , pages_(new QStackedWidget(this))
{
    setWindowTitle(tr("NeuroTendrils"));
    resize(1024, 720);
    setMinimumSize(900, 600);

    auto *centralWidget = new QWidget(this);
    centralWidget->setObjectName(QStringLiteral("appRoot"));
    auto *layout = new QHBoxLayout(centralWidget);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    auto *sidebar = new QWidget(centralWidget);
    sidebar->setObjectName(QStringLiteral("sidebar"));
    sidebar->setFixedWidth(252);
    auto *sidebarLayout = new QVBoxLayout(sidebar);
    sidebarLayout->setContentsMargins(16, 22, 16, 0);
    sidebarLayout->setSpacing(6);

    auto *brand = new QWidget(sidebar);
    auto *brandLayout = new QHBoxLayout(brand);
    brandLayout->setContentsMargins(10, 0, 0, 18);
    brandLayout->setSpacing(0);

    auto *brandNeuro = new QLabel(tr("Neuro"), brand);
    brandNeuro->setObjectName(QStringLiteral("brandNeuro"));
    auto *brandTendrils = new QLabel(tr("Tendrils"), brand);
    brandTendrils->setObjectName(QStringLiteral("brandTendrils"));
    brandLayout->addWidget(brandNeuro);
    brandLayout->addWidget(brandTendrils);
    brandLayout->addStretch();

    navigation_->setAccessibleName(tr("Module navigation"));
    navigation_->setObjectName(QStringLiteral("moduleNavigation"));
    navigation_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    navigation_->setIconSize(QSize(18, 18));
    navigation_->addItem(tr("NeuroFlow"));
    navigation_->addItem(tr("NeuroStudio"));
    navigation_->addItem(tr("NeuroLearn"));
    navigation_->addItem(tr("Hub"));

    // User placeholder card: avatar, name, cloud storage, settings gear.
    // Sign-in and cloud storage become functional in a later phase.
    auto *userCard = new QWidget(sidebar);
    userCard->setObjectName(QStringLiteral("userCard"));
    auto *userLayout = new QHBoxLayout(userCard);
    userLayout->setContentsMargins(10, 14, 6, 14);
    userLayout->setSpacing(12);

    avatarLabel_->setFixedSize(32, 32);

    auto *userText = new QWidget(userCard);
    auto *userTextLayout = new QVBoxLayout(userText);
    userTextLayout->setContentsMargins(0, 0, 0, 0);
    userTextLayout->setSpacing(1);

    auto *userName = new QLabel(tr("Guest"), userText);
    userName->setObjectName(QStringLiteral("userName"));

    auto *storageBar = new QProgressBar(userText);
    storageBar->setObjectName(QStringLiteral("storageBar"));
    storageBar->setAccessibleName(tr("Cloud storage used"));
    storageBar->setRange(0, 1024);
    storageBar->setValue(0);
    storageBar->setTextVisible(false);
    storageBar->setFixedHeight(4);

    auto *userStorage = new QLabel(tr("0 MB of 1 GB"), userText);
    userStorage->setObjectName(QStringLiteral("userStorage"));

    userTextLayout->addWidget(userName);
    userTextLayout->addSpacing(3);
    userTextLayout->addWidget(storageBar);
    userTextLayout->addSpacing(2);
    userTextLayout->addWidget(userStorage);

    settingsButton_->setObjectName(QStringLiteral("settingsButton"));
    settingsButton_->setAccessibleName(tr("Open settings"));
    settingsButton_->setToolTip(tr("Settings"));
    settingsButton_->setCursor(Qt::PointingHandCursor);
    settingsButton_->setIconSize(QSize(18, 18));
    settingsButton_->setAutoRaise(true);

    userLayout->addWidget(avatarLabel_);
    userLayout->addWidget(userText, 1);
    userLayout->addWidget(settingsButton_);

    sidebarLayout->addWidget(brand);
    sidebarLayout->addWidget(navigation_, 1);
    sidebarLayout->addWidget(userCard);

    pages_->addWidget(new NeuroFlowPage(pages_));
    pages_->addWidget(new NeuroStudioPage(pages_));
    pages_->addWidget(new NeuroLearnPage(pages_));
    pages_->addWidget(new HubPage(pages_));

    layout->addWidget(sidebar);
    layout->addWidget(pages_, 1);
    setCentralWidget(centralWidget);

    connect(navigation_,
            &QListWidget::currentRowChanged,
            pages_,
            &QStackedWidget::setCurrentIndex);

    connect(settingsButton_, &QToolButton::clicked, this, [this] {
        if (settingsDialog_ == nullptr) {
            settingsDialog_ = new SettingsDialog(this);
        }
        // open() presents window-modal: a sheet attached to this window
        // on macOS, a regular modal dialog elsewhere.
        settingsDialog_->open();
    });

    connect(&Theme::instance(), &Theme::changed, this, &MainWindow::applyIcons);

    applyIcons();
    navigation_->setCurrentRow(0);
}

MainWindow::~MainWindow() = default;

void MainWindow::applyIcons()
{
    const Theme &theme = Theme::instance();
    const QColor normal = theme.mutedTextColor();
    const QColor selected = theme.textColor();

    navigation_->item(0)->setIcon(icons::icon(icons::Glyph::Flow, normal, selected));
    navigation_->item(1)->setIcon(icons::icon(icons::Glyph::Studio, normal, selected));
    navigation_->item(2)->setIcon(icons::icon(icons::Glyph::Learn, normal, selected));
    navigation_->item(3)->setIcon(icons::icon(icons::Glyph::Hub, normal, selected));
    settingsButton_->setIcon(icons::icon(icons::Glyph::Settings, normal, selected));

    const qreal ratio = devicePixelRatioF();
    QColor avatarBackground = theme.mutedTextColor();
    avatarBackground.setAlpha(60);
    avatarLabel_->setPixmap(icons::avatar(32, ratio, avatarBackground, theme.mutedTextColor()));
}

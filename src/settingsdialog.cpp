#include "settingsdialog.hpp"

#include "core/projectdir.hpp"
#include "core/pythonruntime.hpp"
#include "core/theme.hpp"
#include "core/workerclient.hpp"
#include "widgets/themepreviewcard.hpp"

#include <QApplication>
#include <QDir>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QListWidget>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QStackedWidget>
#include <QVBoxLayout>

SettingsDialog::SettingsDialog(QWidget *parent)
    : QDialog(parent)
    , nav_(new QListWidget(this))
    , panes_(new QStackedWidget(this))
    , workerClient_(new WorkerClient(this))
{
    setWindowTitle(tr("Settings"));
    // Window-modal so it presents as a native sheet on macOS instead of
    // a detached popup window.
    setWindowModality(Qt::WindowModal);
    resize(720, 480);

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
    nav_->addItem(tr("Diagnostics"));

    sidebarLayout->addWidget(navTitle);
    sidebarLayout->addWidget(nav_, 1);

    panes_->addWidget(createAppearancePane());
    panes_->addWidget(createInfoPane());
    panes_->addWidget(createDiagnosticsPane());

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

    connect(workerClient_, &WorkerClient::logMessage, this, &SettingsDialog::appendDiagnosticLog);
    connect(workerClient_,
            &WorkerClient::finished,
            this,
            [this](bool ok, const QJsonObject &result, const QString &errorCode,
                   const QString &errorMessage) {
                if (selfTestStep_ == SelfTestStep::Ping) {
                    if (!ok) {
                        ipcStatusLabel_->setText(
                            tr("Self-test failed on ping: %1 (%2)").arg(errorMessage, errorCode));
                        selfTestStep_ = SelfTestStep::Idle;
                        setDiagnosticsBusy(false);
                        return;
                    }
                    appendDiagnosticLog(tr("ping ok: %1").arg(QString::fromUtf8(
                        QJsonDocument(result).toJson(QJsonDocument::Compact))));
                    selfTestStep_ = SelfTestStep::Echo;
                    workerClient_->startRequest(
                        QStringLiteral("neuroflow"),
                        QStringLiteral("echo"),
                        QJsonObject{{QStringLiteral("hello"), QStringLiteral("neurotendrils")}},
                        15000);
                    return;
                }

                if (selfTestStep_ == SelfTestStep::Echo) {
                    if (!ok) {
                        ipcStatusLabel_->setText(
                            tr("Self-test failed on echo: %1 (%2)").arg(errorMessage, errorCode));
                    } else {
                        const QJsonObject echo = result.value(QStringLiteral("echo")).toObject();
                        const bool matched =
                            echo.value(QStringLiteral("hello")).toString()
                            == QStringLiteral("neurotendrils");
                        if (matched) {
                            ipcStatusLabel_->setText(tr("Self-test passed."));
                        } else {
                            ipcStatusLabel_->setText(tr("Self-test failed: unexpected echo payload."));
                        }
                        appendDiagnosticLog(tr("echo ok: %1").arg(QString::fromUtf8(
                            QJsonDocument(result).toJson(QJsonDocument::Compact))));
                    }
                    selfTestStep_ = SelfTestStep::Idle;
                    setDiagnosticsBusy(false);
                }
            });
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

    auto *projectTitle = new QLabel(tr("Project folder"), pane);
    projectTitle->setObjectName(QStringLiteral("settingTitle"));

    auto *projectPath =
        new QLabel(QDir::toNativeSeparators(ProjectDir::instance().root()), pane);
    projectPath->setObjectName(QStringLiteral("settingDescription"));
    projectPath->setWordWrap(true);
    projectPath->setTextInteractionFlags(Qt::TextSelectableByMouse);

    auto *pythonTitle = new QLabel(tr("Python runtime"), pane);
    pythonTitle->setObjectName(QStringLiteral("settingTitle"));

    const PythonRuntime &python = PythonRuntime::instance();
    QString pythonText;
    if (python.isAvailable()) {
        pythonText = QDir::toNativeSeparators(python.interpreterPath());
        if (!python.sourceDescription().isEmpty()) {
            pythonText += QStringLiteral(" (%1)").arg(python.sourceDescription());
        }
    } else {
        pythonText = tr("Not found. Run python/setup_venv.sh (or .ps1) to create .venv.");
    }
    auto *pythonPath = new QLabel(pythonText, pane);
    pythonPath->setObjectName(QStringLiteral("settingDescription"));
    pythonPath->setWordWrap(true);
    pythonPath->setTextInteractionFlags(Qt::TextSelectableByMouse);

    layout->addWidget(title);
    layout->addSpacing(20);
    layout->addWidget(name);
    layout->addSpacing(4);
    layout->addWidget(version);
    layout->addSpacing(2);
    layout->addWidget(description);
    layout->addSpacing(18);
    layout->addWidget(projectTitle);
    layout->addSpacing(4);
    layout->addWidget(projectPath);
    layout->addSpacing(18);
    layout->addWidget(pythonTitle);
    layout->addSpacing(4);
    layout->addWidget(pythonPath);
    layout->addStretch();

    return pane;
}

QWidget *SettingsDialog::createDiagnosticsPane()
{
    auto *pane = new QWidget(this);
    auto *layout = new QVBoxLayout(pane);
    layout->setContentsMargins(32, 28, 32, 24);
    layout->setSpacing(0);

    auto *title = new QLabel(tr("Diagnostics"), pane);
    title->setObjectName(QStringLiteral("pageTitle"));

    auto *blurb = new QLabel(
        tr("Verify that the suite can launch NeuroFlow over argv-only JSON-lines IPC."),
        pane);
    blurb->setObjectName(QStringLiteral("settingDescription"));
    blurb->setWordWrap(true);

    ipcTestButton_ = new QPushButton(tr("Run IPC self-test"), pane);
    ipcTestButton_->setAutoDefault(false);
    connect(ipcTestButton_, &QPushButton::clicked, this, &SettingsDialog::runIpcSelfTest);

    ipcStatusLabel_ = new QLabel(tr("Not run yet."), pane);
    ipcStatusLabel_->setObjectName(QStringLiteral("settingDescription"));
    ipcStatusLabel_->setWordWrap(true);

    ipcLog_ = new QPlainTextEdit(pane);
    ipcLog_->setObjectName(QStringLiteral("diagnosticsLog"));
    ipcLog_->setReadOnly(true);
    ipcLog_->setPlaceholderText(tr("Worker log (redacted)…"));
    ipcLog_->setMinimumHeight(160);

    layout->addWidget(title);
    layout->addSpacing(12);
    layout->addWidget(blurb);
    layout->addSpacing(16);
    layout->addWidget(ipcTestButton_, 0, Qt::AlignLeft);
    layout->addSpacing(8);
    layout->addWidget(ipcStatusLabel_);
    layout->addSpacing(12);
    layout->addWidget(ipcLog_, 1);

    return pane;
}

void SettingsDialog::syncCards()
{
    const ThemeMode mode = Theme::instance().mode();
    lightCard_->setChecked(mode == ThemeMode::Light);
    darkCard_->setChecked(mode == ThemeMode::Dark);
    autoCard_->setChecked(mode == ThemeMode::System);
}

void SettingsDialog::runIpcSelfTest()
{
    if (workerClient_->isBusy() || selfTestStep_ != SelfTestStep::Idle) {
        return;
    }

    ipcLog_->clear();
    ipcStatusLabel_->setText(tr("Running ping…"));
    setDiagnosticsBusy(true);
    selfTestStep_ = SelfTestStep::Ping;
    workerClient_->startRequest(QStringLiteral("neuroflow"), QStringLiteral("ping"), {}, 15000);
}

void SettingsDialog::appendDiagnosticLog(const QString &line)
{
    if (ipcLog_ == nullptr || line.trimmed().isEmpty()) {
        return;
    }
    ipcLog_->appendPlainText(line);
}

void SettingsDialog::setDiagnosticsBusy(bool busy)
{
    if (ipcTestButton_ != nullptr) {
        ipcTestButton_->setEnabled(!busy);
    }
}

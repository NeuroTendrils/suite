#include "modules/neuroflow/neuroflowpage.hpp"

#include "core/datasetimport.hpp"
#include "core/planio.hpp"
#include "core/plangenerator.hpp"
#include "core/projectdir.hpp"
#include "core/runio.hpp"
#include "core/stepcatalog.hpp"
#include "core/theme.hpp"
#include "core/workerclient.hpp"
#include "modules/neuroflow/stepeditdialog.hpp"
#include "widgets/icons.hpp"
#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFontMetrics>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QMessageBox>
#include <QPushButton>
#include <QResizeEvent>
#include <QScrollArea>
#include <QSizePolicy>
#include <QStackedWidget>
#include <QVBoxLayout>

namespace
{
void makeFlexible(QWidget *widget)
{
    widget->setMinimumWidth(0);
    auto policy = widget->sizePolicy();
    policy.setHorizontalPolicy(QSizePolicy::Expanding);
    widget->setSizePolicy(policy);
}

QFrame *makePanel(const QString &objectName, QWidget *parent)
{
    auto *frame = new QFrame(parent);
    frame->setObjectName(objectName);
    frame->setFrameShape(QFrame::NoFrame);
    makeFlexible(frame);
    frame->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    return frame;
}
} // namespace

NeuroFlowPage::NeuroFlowPage(QWidget *parent)
    : QWidget(parent)
    , workerClient_(new WorkerClient(this))
{
    makeFlexible(this);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    auto *rootLayout = new QVBoxLayout(this);
    rootLayout->setContentsMargins(0, 0, 0, 0);
    rootLayout->setSpacing(0);

    auto *scroll = new QScrollArea(this);
    scroll->setObjectName(QStringLiteral("pageScroll"));
    scroll->setWidgetResizable(true);
    scroll->setFrameShape(QFrame::NoFrame);
    scroll->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    scroll->viewport()->setMinimumWidth(0);

    auto *content = new QWidget;
    content->setObjectName(QStringLiteral("pageContent"));
    makeFlexible(content);
    content->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    auto *layout = new QVBoxLayout(content);
    layout->setContentsMargins(20, 16, 20, 20);
    layout->setSpacing(0);

    auto *header = new PageHeader(
        tr("NeuroFlow"), tr("Build and run reproducible EEG preprocessing plans."), content);

    auto *recordingLabel = new QLabel(tr("Recording"), content);
    recordingLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(recordingLabel);

    recordingStack_ = new QStackedWidget(content);
    makeFlexible(recordingStack_);
    recordingStack_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    // --- Empty state ---
    auto *emptyPanel = makePanel(QStringLiteral("emptyPanel"), recordingStack_);
    auto *emptyLayout = new QVBoxLayout(emptyPanel);
    emptyLayout->setContentsMargins(16, 18, 16, 18);
    emptyLayout->setSpacing(0);

    emptyIconLabel_ = new QLabel(emptyPanel);
    emptyIconLabel_->setAlignment(Qt::AlignHCenter | Qt::AlignVCenter);
    emptyIconLabel_->setFixedHeight(28);
    makeFlexible(emptyIconLabel_);

    auto *emptyTitle = new QLabel(tr("Add a recording"), emptyPanel);
    emptyTitle->setObjectName(QStringLiteral("emptyPanelTitle"));
    emptyTitle->setAlignment(Qt::AlignHCenter | Qt::AlignVCenter);
    emptyTitle->setWordWrap(true);
    makeFlexible(emptyTitle);

    emptyHint_ = new QLabel(tr("EDF, BDF, FIF, and more. Outside files copy into datasets/."),
                            emptyPanel);
    emptyHint_->setObjectName(QStringLiteral("emptyPanelHint"));
    emptyHint_->setAlignment(Qt::AlignHCenter | Qt::AlignTop);
    emptyHint_->setWordWrap(true);
    makeFlexible(emptyHint_);
    emptyHint_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    auto *chooseButton = new QPushButton(tr("Choose file"), emptyPanel);
    chooseButton->setObjectName(QStringLiteral("primaryButton"));
    chooseButton->setCursor(Qt::PointingHandCursor);
    chooseButton->setAutoDefault(false);

    auto *chooseRow = new QWidget(emptyPanel);
    makeFlexible(chooseRow);
    auto *chooseRowLayout = new QHBoxLayout(chooseRow);
    chooseRowLayout->setContentsMargins(0, 0, 0, 0);
    chooseRowLayout->addStretch();
    chooseRowLayout->addWidget(chooseButton);
    chooseRowLayout->addStretch();

    connect(chooseButton, &QPushButton::clicked, this, &NeuroFlowPage::importRecording);

    emptyLayout->addWidget(emptyIconLabel_);
    emptyLayout->addSpacing(8);
    emptyLayout->addWidget(emptyTitle);
    emptyLayout->addSpacing(4);
    emptyLayout->addWidget(emptyHint_);
    emptyLayout->addSpacing(12);
    emptyLayout->addWidget(chooseRow);

    // --- Selected file state ---
    auto *filePanel = makePanel(QStringLiteral("filePanel"), recordingStack_);
    auto *fileLayout = new QVBoxLayout(filePanel);
    fileLayout->setContentsMargins(12, 12, 12, 12);
    fileLayout->setSpacing(8);

    auto *topRow = new QWidget(filePanel);
    makeFlexible(topRow);
    auto *topLayout = new QHBoxLayout(topRow);
    topLayout->setContentsMargins(0, 0, 0, 0);
    topLayout->setSpacing(10);

    fileIconLabel_ = new QLabel(topRow);
    fileIconLabel_->setFixedSize(28, 28);
    fileIconLabel_->setAlignment(Qt::AlignCenter);

    auto *fileText = new QWidget(topRow);
    makeFlexible(fileText);
    fileText->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    auto *fileTextLayout = new QVBoxLayout(fileText);
    fileTextLayout->setContentsMargins(0, 0, 0, 0);
    fileTextLayout->setSpacing(2);

    auto *titleRow = new QWidget(fileText);
    makeFlexible(titleRow);
    auto *titleRowLayout = new QHBoxLayout(titleRow);
    titleRowLayout->setContentsMargins(0, 0, 0, 0);
    titleRowLayout->setSpacing(6);

    fileNameLabel_ = new QLabel(titleRow);
    fileNameLabel_->setObjectName(QStringLiteral("fileNameLabel"));
    makeFlexible(fileNameLabel_);
    fileNameLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);

    fileBadge_ = new QLabel(titleRow);
    fileBadge_->setObjectName(QStringLiteral("fileBadge"));
    fileBadge_->setVisible(false);

    titleRowLayout->addWidget(fileNameLabel_, 1);
    titleRowLayout->addWidget(fileBadge_, 0, Qt::AlignVCenter);

    fileMetaLabel_ = new QLabel(fileText);
    fileMetaLabel_->setObjectName(QStringLiteral("fileMetaLabel"));
    fileMetaLabel_->setWordWrap(true);
    makeFlexible(fileMetaLabel_);

    filePathLabel_ = new QLabel(fileText);
    filePathLabel_->setObjectName(QStringLiteral("filePathLabel"));
    makeFlexible(filePathLabel_);
    filePathLabel_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Preferred);
    filePathLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);

    fileTextLayout->addWidget(titleRow);
    fileTextLayout->addWidget(fileMetaLabel_);
    fileTextLayout->addWidget(filePathLabel_);

    topLayout->addWidget(fileIconLabel_, 0, Qt::AlignTop);
    topLayout->addWidget(fileText, 1);

    auto *actions = new QWidget(filePanel);
    makeFlexible(actions);
    auto *actionsLayout = new QHBoxLayout(actions);
    actionsLayout->setContentsMargins(0, 0, 0, 0);
    actionsLayout->setSpacing(8);

    changeButton_ = new QPushButton(tr("Change"), actions);
    changeButton_->setObjectName(QStringLiteral("secondaryButton"));
    changeButton_->setCursor(Qt::PointingHandCursor);
    changeButton_->setAutoDefault(false);
    connect(changeButton_, &QPushButton::clicked, this, &NeuroFlowPage::importRecording);

    clearButton_ = new QPushButton(tr("Clear"), actions);
    clearButton_->setObjectName(QStringLiteral("secondaryButton"));
    clearButton_->setCursor(Qt::PointingHandCursor);
    clearButton_->setAutoDefault(false);
    connect(clearButton_, &QPushButton::clicked, this, &NeuroFlowPage::clearRecording);

    actionsLayout->addWidget(changeButton_);
    actionsLayout->addWidget(clearButton_);
    actionsLayout->addStretch();

    fileLayout->addWidget(topRow);
    fileLayout->addWidget(actions);

    recordingStack_->addWidget(emptyPanel);
    recordingStack_->addWidget(filePanel);
    recordingStack_->setCurrentIndex(0);

    auto *fingerprintLabel = new QLabel(tr("Fingerprint"), content);
    fingerprintLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(fingerprintLabel);

    auto *fingerprintPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *fingerprintLayout = new QVBoxLayout(fingerprintPanel);
    fingerprintLayout->setContentsMargins(12, 12, 12, 12);
    fingerprintLayout->setSpacing(8);

    fingerprintStatus_ = new QLabel(fingerprintPanel);
    fingerprintStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    fingerprintStatus_->setWordWrap(true);
    makeFlexible(fingerprintStatus_);

    fingerprintSkeleton_ = new SkeletonLoader(fingerprintPanel);
    makeFlexible(fingerprintSkeleton_);
    fingerprintSkeleton_->addBlock(0.28, 10, 4);
    fingerprintSkeleton_->addBlock(0.9, 10, 4);
    fingerprintSkeleton_->addBlock(0.62, 10, 4);

    fingerprintCard_ = new QWidget(fingerprintPanel);
    makeFlexible(fingerprintCard_);
    fingerprintCard_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    auto *cardLayout = new QGridLayout(fingerprintCard_);
    cardLayout->setContentsMargins(0, 0, 0, 0);
    cardLayout->setHorizontalSpacing(16);
    cardLayout->setVerticalSpacing(8);

    auto makeKey = [](const QString &text, QWidget *parent) {
        auto *label = new QLabel(text, parent);
        label->setObjectName(QStringLiteral("fingerprintKey"));
        makeFlexible(label);
        return label;
    };
    auto makeValue = [](QWidget *parent) {
        auto *label = new QLabel(parent);
        label->setObjectName(QStringLiteral("fingerprintValue"));
        label->setWordWrap(true);
        makeFlexible(label);
        return label;
    };

    fpChannelsValue_ = makeValue(fingerprintCard_);
    fpSfreqValue_ = makeValue(fingerprintCard_);
    fpDurationValue_ = makeValue(fingerprintCard_);
    fpMontageValue_ = makeValue(fingerprintCard_);
    fpFiltersValue_ = makeValue(fingerprintCard_);

    cardLayout->addWidget(makeKey(tr("Channels"), fingerprintCard_), 0, 0);
    cardLayout->addWidget(fpChannelsValue_, 1, 0);
    cardLayout->addWidget(makeKey(tr("Sampling rate"), fingerprintCard_), 0, 1);
    cardLayout->addWidget(fpSfreqValue_, 1, 1);
    cardLayout->addWidget(makeKey(tr("Duration"), fingerprintCard_), 0, 2);
    cardLayout->addWidget(fpDurationValue_, 1, 2);
    cardLayout->addWidget(makeKey(tr("Montage"), fingerprintCard_), 2, 0);
    cardLayout->addWidget(fpMontageValue_, 3, 0);
    cardLayout->addWidget(makeKey(tr("Filters"), fingerprintCard_), 2, 1, 1, 2);
    cardLayout->addWidget(fpFiltersValue_, 3, 1, 1, 2);

    auto *channelNamesKey = makeKey(tr("Channel names"), fingerprintCard_);
    fpChannelNames_ = new QLabel(fingerprintCard_);
    fpChannelNames_->setObjectName(QStringLiteral("fingerprintChannels"));
    fpChannelNames_->setWordWrap(true);
    makeFlexible(fpChannelNames_);

    cardLayout->addWidget(channelNamesKey, 4, 0, 1, 3);
    cardLayout->addWidget(fpChannelNames_, 5, 0, 1, 3);
    cardLayout->setColumnStretch(0, 1);
    cardLayout->setColumnStretch(1, 1);
    cardLayout->setColumnStretch(2, 1);

    fingerprintLayout->addWidget(fingerprintStatus_);
    fingerprintLayout->addWidget(fingerprintSkeleton_);
    fingerprintLayout->addWidget(fingerprintCard_);

    auto *planLabel = new QLabel(tr("Plan"), content);
    planLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(planLabel);

    auto *planPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *planLayout = new QVBoxLayout(planPanel);
    planLayout->setContentsMargins(12, 12, 12, 12);
    planLayout->setSpacing(8);

    planStatus_ = new QLabel(planPanel);
    planStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    planStatus_->setWordWrap(true);
    makeFlexible(planStatus_);

    planListHost_ = new QWidget(planPanel);
    makeFlexible(planListHost_);
    planListHost_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);
    planListLayout_ = new QVBoxLayout(planListHost_);
    planListLayout_->setContentsMargins(0, 0, 0, 0);
    planListLayout_->setSpacing(8);

    addStepButton_ = new QPushButton(tr("Add step"), planPanel);
    addStepButton_->setObjectName(QStringLiteral("secondaryButton"));
    addStepButton_->setCursor(Qt::PointingHandCursor);
    addStepButton_->setAutoDefault(false);
    connect(addStepButton_, &QPushButton::clicked, this, &NeuroFlowPage::addPlanStep);

    savePlanButton_ = new QPushButton(tr("Save plan"), planPanel);
    savePlanButton_->setObjectName(QStringLiteral("secondaryButton"));
    savePlanButton_->setCursor(Qt::PointingHandCursor);
    savePlanButton_->setAutoDefault(false);
    connect(savePlanButton_, &QPushButton::clicked, this, &NeuroFlowPage::savePlan);

    loadPlanButton_ = new QPushButton(tr("Load plan"), planPanel);
    loadPlanButton_->setObjectName(QStringLiteral("secondaryButton"));
    loadPlanButton_->setCursor(Qt::PointingHandCursor);
    loadPlanButton_->setAutoDefault(false);
    connect(loadPlanButton_, &QPushButton::clicked, this, &NeuroFlowPage::loadPlan);

    planActions_ = new QWidget(planPanel);
    makeFlexible(planActions_);
    auto *planActionsLayout = new QHBoxLayout(planActions_);
    planActionsLayout->setContentsMargins(0, 0, 0, 0);
    planActionsLayout->setSpacing(8);
    planActionsLayout->addWidget(addStepButton_, 0, Qt::AlignLeft);
    planActionsLayout->addWidget(savePlanButton_, 0, Qt::AlignLeft);
    planActionsLayout->addWidget(loadPlanButton_, 0, Qt::AlignLeft);
    planActionsLayout->addStretch(1);
    planActions_->setVisible(false);

    planLayout->addWidget(planStatus_);
    planLayout->addWidget(planListHost_);
    planLayout->addWidget(planActions_);

    auto *runLabel = new QLabel(tr("Run"), content);
    runLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(runLabel);

    auto *runPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *runLayout = new QVBoxLayout(runPanel);
    runLayout->setContentsMargins(12, 12, 12, 12);
    runLayout->setSpacing(8);

    runStatus_ = new QLabel(runPanel);
    runStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    runStatus_->setWordWrap(true);
    makeFlexible(runStatus_);

    runSkeleton_ = new SkeletonLoader(runPanel);
    runSkeleton_->addBlock(0.9, 14, 6);
    runSkeleton_->addBlock(0.7, 14, 6);
    runSkeleton_->addBlock(0.5, 14, 6);
    runSkeleton_->setVisible(false);

    runResult_ = new QLabel(runPanel);
    runResult_->setObjectName(QStringLiteral("upcomingCaption"));
    runResult_->setWordWrap(true);
    runResult_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    runResult_->setVisible(false);
    makeFlexible(runResult_);

    runLog_ = new QLabel(runPanel);
    runLog_->setObjectName(QStringLiteral("upcomingCaption"));
    runLog_->setWordWrap(true);
    runLog_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    runLog_->setVisible(false);
    makeFlexible(runLog_);

    runPlanButton_ = new QPushButton(tr("Run plan"), runPanel);
    runPlanButton_->setObjectName(QStringLiteral("primaryButton"));
    runPlanButton_->setCursor(Qt::PointingHandCursor);
    runPlanButton_->setAutoDefault(false);
    connect(runPlanButton_, &QPushButton::clicked, this, &NeuroFlowPage::runPlan);

    cancelRunButton_ = new QPushButton(tr("Cancel"), runPanel);
    cancelRunButton_->setObjectName(QStringLiteral("secondaryButton"));
    cancelRunButton_->setCursor(Qt::PointingHandCursor);
    cancelRunButton_->setAutoDefault(false);
    cancelRunButton_->setVisible(false);
    connect(cancelRunButton_, &QPushButton::clicked, this, &NeuroFlowPage::cancelWorker);

    auto *runActions = new QWidget(runPanel);
    makeFlexible(runActions);
    auto *runActionsLayout = new QHBoxLayout(runActions);
    runActionsLayout->setContentsMargins(0, 0, 0, 0);
    runActionsLayout->setSpacing(8);
    runActionsLayout->addWidget(runPlanButton_, 0, Qt::AlignLeft);
    runActionsLayout->addWidget(cancelRunButton_, 0, Qt::AlignLeft);
    runActionsLayout->addStretch(1);

    runLayout->addWidget(runStatus_);
    runLayout->addWidget(runSkeleton_);
    runLayout->addWidget(runResult_);
    runLayout->addWidget(runLog_);
    runLayout->addWidget(runActions);

    layout->addWidget(header);
    layout->addSpacing(16);
    layout->addWidget(recordingLabel);
    layout->addSpacing(6);
    layout->addWidget(recordingStack_);
    layout->addSpacing(16);
    layout->addWidget(fingerprintLabel);
    layout->addSpacing(6);
    layout->addWidget(fingerprintPanel);
    layout->addSpacing(16);
    layout->addWidget(planLabel);
    layout->addSpacing(6);
    layout->addWidget(planPanel);
    layout->addSpacing(16);
    layout->addWidget(runLabel);
    layout->addSpacing(6);
    layout->addWidget(runPanel);
    layout->addStretch(1);

    scroll->setWidget(content);
    rootLayout->addWidget(scroll);

    connect(&Theme::instance(), &Theme::changed, this, &NeuroFlowPage::refreshIcons);
    connect(workerClient_, &WorkerClient::finished, this, &NeuroFlowPage::onWorkerFinished);
    connect(workerClient_, &WorkerClient::logMessage, this, &NeuroFlowPage::onWorkerLog);
    connect(workerClient_, &WorkerClient::eventReceived, this, &NeuroFlowPage::onWorkerEvent);
    refreshIcons();
    setFingerprintIdle();
    setPlanIdle();
    setRunIdle();
}

QString NeuroFlowPage::currentDatasetPath() const
{
    return datasetPath_;
}

QJsonObject NeuroFlowPage::currentFingerprint() const
{
    return fingerprint_;
}

PlanGenerator::Plan NeuroFlowPage::currentPlan() const
{
    return plan_;
}

void NeuroFlowPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateElidedTexts();
}

void NeuroFlowPage::importRecording()
{
    if (ProjectDir::instance().root().isEmpty()) {
        QMessageBox::warning(this, tr("No project folder"),
                             tr("Configure a project folder before importing recordings."));
        return;
    }

    const QString source = QFileDialog::getOpenFileName(
        this,
        tr("Import EEG recording"),
        QDir::homePath(),
        DatasetImport::fileFilters().join(QStringLiteral(";;")));
    if (source.isEmpty()) {
        return;
    }

    const DatasetImport::Result result = DatasetImport::importRecording(source);
    if (!result.ok) {
        QMessageBox::warning(this, tr("Import failed"), result.error);
        return;
    }

    setDatasetPath(result.datasetPath, result.copied);
}

void NeuroFlowPage::clearRecording()
{
    cancelWorker();
    datasetPath_.clear();
    fullFileName_.clear();
    fullFilePath_.clear();
    fingerprint_ = {};
    clearPlan();
    runOutputPath_.clear();
    runMetadataPath_.clear();
    fileNameLabel_->clear();
    fileMetaLabel_->clear();
    filePathLabel_->clear();
    filePathLabel_->setToolTip(QString());
    fileNameLabel_->setToolTip(QString());
    fileBadge_->clear();
    fileBadge_->setVisible(false);
    recordingStack_->setCurrentIndex(0);
    setFingerprintIdle();
    setPlanIdle();
    setRunIdle();
}

void NeuroFlowPage::setDatasetPath(const QString &path, bool copied)
{
    cancelWorker();

    datasetPath_ = path;
    fingerprint_ = {};
    // Keep a loaded/edited plan when attaching a recording; only wipe
    // auto-generated plans so the new fingerprint can replace them.
    if (!planUserOwned_) {
        clearPlan();
        setPlanIdle();
    }
    runOutputPath_.clear();
    runMetadataPath_.clear();
    setRunIdle();
    const QFileInfo info(path);

    fullFileName_ = info.fileName();
    fullFilePath_ = QDir::toNativeSeparators(path);

    fileMetaLabel_->setText(
        tr("%1 · %2")
            .arg(formatFileSize(info.size()),
                 copied ? tr("Copied into datasets/")
                        : tr("Already in project folder")));

    const QString suffix = info.suffix().toUpper();
    if (!suffix.isEmpty()) {
        fileBadge_->setText(suffix);
        fileBadge_->setVisible(true);
    } else {
        fileBadge_->setVisible(false);
    }

    recordingStack_->setCurrentIndex(1);
    refreshIcons();
    updateElidedTexts();
    requestFingerprint();
}

void NeuroFlowPage::requestFingerprint()
{
    if (datasetPath_.isEmpty()) {
        setFingerprintIdle();
        return;
    }

    if (!ProjectDir::instance().contains(datasetPath_)) {
        setFingerprintError(tr("Recording is outside the project folder."));
        return;
    }

    if (WorkerClient::workersRoot().isEmpty()) {
        setFingerprintError(tr("NeuroFlow worker not found."));
        return;
    }

    if (workerClient_->isBusy()) {
        setFingerprintError(tr("A worker is already running."));
        return;
    }

    setFingerprintLoading();
    pendingOp_ = WorkerOp::Fingerprint;
    workerClient_->startRequest(
        QStringLiteral("neuroflow"),
        QStringLiteral("fingerprint"),
        QJsonObject{{QStringLiteral("path"), datasetPath_}},
        60000);
}

void NeuroFlowPage::cancelWorker()
{
    if (workerClient_ != nullptr && workerClient_->isBusy()) {
        workerClient_->cancel();
    }
}

void NeuroFlowPage::onWorkerFinished(bool ok,
                                     const QJsonObject &result,
                                     const QString &errorCode,
                                     const QString &errorMessage)
{
    const WorkerOp op = pendingOp_;
    pendingOp_ = WorkerOp::None;

    if (errorCode == QLatin1String("cancelled")) {
        if (op == WorkerOp::Run) {
            setRunError(tr("Run cancelled."));
        }
        updateRunActionsEnabled();
        return;
    }

    if (op == WorkerOp::Run) {
        if (!ok) {
            const QString detail = errorMessage.isEmpty() ? errorCode : errorMessage;
            setRunError(tr("Run failed: %1").arg(detail));
            return;
        }

        QString outputPath = result.value(QStringLiteral("output_path")).toString();
        if (outputPath.isEmpty()) {
            outputPath = runOutputPath_;
        }
        if (!ProjectDir::instance().contains(outputPath)) {
            setRunError(tr("Worker wrote outside the project folder."));
            return;
        }

        const RunIo::Result meta = RunIo::writeMetadata(
            runMetadataPath_,
            datasetPath_,
            outputPath,
            plan_,
            planPath_,
            result);
        if (!meta.ok) {
            setRunError(tr("Run finished but metadata failed: %1").arg(meta.error));
            return;
        }

        runOutputPath_ = outputPath;
        runMetadataPath_ = meta.path;
        setRunReady(result, outputPath, meta.path);
        return;
    }

    if (op != WorkerOp::Fingerprint) {
        return;
    }

    if (datasetPath_.isEmpty()) {
        setFingerprintIdle();
        return;
    }

    if (!ok) {
        const QString detail = errorMessage.isEmpty() ? errorCode : errorMessage;
        setFingerprintError(tr("Could not fingerprint recording: %1").arg(detail));
        return;
    }

    setFingerprintReady(result);
}

void NeuroFlowPage::onWorkerLog(const QString &redactedLine)
{
    if (pendingOp_ != WorkerOp::Run || runLog_ == nullptr) {
        return;
    }
    // Progress lines also arrive via stderr; keep the status label current.
    if (redactedLine.startsWith(QLatin1String("Step "))
        || redactedLine.startsWith(QLatin1String("Loading "))
        || redactedLine.startsWith(QLatin1String("Writing "))) {
        runStatus_->setText(redactedLine);
    }
    runLog_->setVisible(true);
    const QString existing = runLog_->text();
    if (existing.isEmpty()) {
        runLog_->setText(redactedLine);
    } else {
        runLog_->setText(existing + QLatin1Char('\n') + redactedLine);
    }
}

void NeuroFlowPage::onWorkerEvent(const QString &requestId,
                                  const QString &name,
                                  const QJsonObject &data)
{
    Q_UNUSED(requestId);
    if (pendingOp_ != WorkerOp::Run || name != QLatin1String("progress")) {
        return;
    }
    const QString message = data.value(QStringLiteral("message")).toString();
    if (!message.isEmpty()) {
        runStatus_->setText(message);
    }
}

void NeuroFlowPage::setFingerprintIdle()
{
    fingerprint_ = {};
    fingerprintStatus_->setText(
        tr("Import a recording to see channels, sampling rate, and duration."));
    fingerprintStatus_->setVisible(true);
    fingerprintSkeleton_->setVisible(false);
    fingerprintCard_->setVisible(false);
}

void NeuroFlowPage::setFingerprintLoading()
{
    fingerprint_ = {};
    if (!planUserOwned_) {
        clearPlan();
        setPlanIdle();
    }
    fingerprintStatus_->setText(tr("Reading recording"));
    fingerprintStatus_->setVisible(true);
    fingerprintSkeleton_->setVisible(true);
    fingerprintCard_->setVisible(false);
}

void NeuroFlowPage::setFingerprintReady(const QJsonObject &result)
{
    fingerprint_ = result;
    populateFingerprintCard(result);
    fingerprintStatus_->setVisible(false);
    fingerprintSkeleton_->setVisible(false);
    fingerprintCard_->setVisible(true);
    // Preserve plans the user loaded or edited; only auto-build when empty.
    if (planUserOwned_ && !PlanGenerator::isEmpty(plan_)) {
        setPlanReady(plan_);
    } else {
        regeneratePlan();
    }
}

void NeuroFlowPage::setFingerprintError(const QString &message)
{
    fingerprint_ = {};
    if (!planUserOwned_) {
        clearPlan();
        setPlanIdle();
    }
    fingerprintStatus_->setText(message);
    fingerprintStatus_->setVisible(true);
    fingerprintSkeleton_->setVisible(false);
    fingerprintCard_->setVisible(false);
}

void NeuroFlowPage::regeneratePlan()
{
    planPath_.clear();
    planUserOwned_ = false;
    plan_ = PlanGenerator::fromFingerprint(fingerprint_);
    // Always show the plan panel after a fingerprint so users can add steps
    // even if heuristics produced an empty starter plan.
    setPlanReady(plan_);
}

void NeuroFlowPage::clearPlan()
{
    plan_ = {};
    planPath_.clear();
    planUserOwned_ = false;
}

void NeuroFlowPage::setPlanIdle()
{
    clearPlanList();
    planStatus_->setText(
        tr("A default step plan appears here after the recording is fingerprinted. "
           "You can also load a saved plan."));
    planStatus_->setToolTip(QString());
    planListHost_->setVisible(false);
    addStepButton_->setVisible(false);
    savePlanButton_->setVisible(false);
    loadPlanButton_->setVisible(true);
    planActions_->setVisible(true);
    updateRunActionsEnabled();
}

void NeuroFlowPage::setPlanReady(const PlanGenerator::Plan &plan)
{
    if (plan.steps.isEmpty()) {
        planStatus_->setText(tr("No steps yet. Add a step to build a plan."));
    } else if (!planPath_.isEmpty()) {
        planStatus_->setText(
            tr("%n step(s) (%1). Edit, reorder, save, or load another plan.",
               nullptr,
               plan.steps.size())
                .arg(QFileInfo(planPath_).fileName()));
    } else {
        planStatus_->setText(
            tr("%n step(s). Edit parameters, reorder with Up/Down, or add/remove steps.",
               nullptr,
               plan.steps.size()));
    }
    planStatus_->setToolTip(QString::fromUtf8(
        QJsonDocument(PlanGenerator::toJson(plan)).toJson(QJsonDocument::Indented)));
    rebuildPlanList(plan);
    planListHost_->setVisible(true);
    addStepButton_->setVisible(true);
    savePlanButton_->setVisible(true);
    savePlanButton_->setEnabled(!plan.steps.isEmpty());
    loadPlanButton_->setVisible(true);
    planActions_->setVisible(true);
    updateRunActionsEnabled();
}

void NeuroFlowPage::refreshPlanUi()
{
    setPlanReady(plan_);
}

void NeuroFlowPage::clearPlanList()
{
    if (planListLayout_ == nullptr) {
        return;
    }
    while (QLayoutItem *item = planListLayout_->takeAt(0)) {
        if (QWidget *widget = item->widget()) {
            widget->deleteLater();
        }
        delete item;
    }
}

void NeuroFlowPage::rebuildPlanList(const PlanGenerator::Plan &plan)
{
    clearPlanList();

    for (int i = 0; i < plan.steps.size(); ++i) {
        const PlanGenerator::Step &step = plan.steps.at(i);

        auto *row = new QFrame(planListHost_);
        row->setObjectName(QStringLiteral("planStepRow"));
        row->setFrameShape(QFrame::NoFrame);
        makeFlexible(row);
        row->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

        auto *rowLayout = new QVBoxLayout(row);
        rowLayout->setContentsMargins(12, 10, 12, 10);
        rowLayout->setSpacing(6);

        auto *header = new QWidget(row);
        makeFlexible(header);
        auto *headerLayout = new QHBoxLayout(header);
        headerLayout->setContentsMargins(0, 0, 0, 0);
        headerLayout->setSpacing(8);

        auto *indexLabel = new QLabel(QString::number(i + 1), header);
        indexLabel->setObjectName(QStringLiteral("planStepIndex"));
        indexLabel->setAlignment(Qt::AlignCenter);
        indexLabel->setFixedSize(24, 24);

        auto *title = new QLabel(step.title, header);
        title->setObjectName(QStringLiteral("planStepTitle"));
        makeFlexible(title);

        auto makeAction = [header](const QString &label) {
            auto *button = new QPushButton(label, header);
            button->setObjectName(QStringLiteral("planStepButton"));
            button->setCursor(Qt::PointingHandCursor);
            button->setAutoDefault(false);
            button->setFlat(false);
            button->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
            return button;
        };

        auto *upButton = makeAction(tr("Up"));
        auto *downButton = makeAction(tr("Down"));
        auto *editButton = makeAction(tr("Edit"));
        auto *removeButton = makeAction(tr("Remove"));

        upButton->setEnabled(i > 0);
        downButton->setEnabled(i + 1 < plan.steps.size());
        upButton->setToolTip(tr("Move step up"));
        downButton->setToolTip(tr("Move step down"));

        connect(editButton, &QPushButton::clicked, this, [this, i]() { editPlanStep(i); });
        connect(upButton, &QPushButton::clicked, this, [this, i]() { movePlanStep(i, -1); });
        connect(downButton, &QPushButton::clicked, this, [this, i]() { movePlanStep(i, 1); });
        connect(removeButton, &QPushButton::clicked, this, [this, i]() { removePlanStep(i); });

        headerLayout->addWidget(indexLabel, 0, Qt::AlignVCenter);
        headerLayout->addWidget(title, 1, Qt::AlignVCenter);
        headerLayout->addWidget(upButton, 0, Qt::AlignVCenter);
        headerLayout->addWidget(downButton, 0, Qt::AlignVCenter);
        headerLayout->addWidget(editButton, 0, Qt::AlignVCenter);
        headerLayout->addWidget(removeButton, 0, Qt::AlignVCenter);

        const QString params = formatStepParams(step.params);
        auto *meta = new QLabel(params.isEmpty() ? step.stepId : params, row);
        meta->setObjectName(QStringLiteral("planStepMeta"));
        meta->setWordWrap(true);
        makeFlexible(meta);

        rowLayout->addWidget(header);
        rowLayout->addWidget(meta);
        if (!step.rationale.isEmpty()) {
            auto *why = new QLabel(step.rationale, row);
            why->setObjectName(QStringLiteral("planStepRationale"));
            why->setWordWrap(true);
            makeFlexible(why);
            rowLayout->addWidget(why);
        }

        planListLayout_->addWidget(row);
    }
}

void NeuroFlowPage::editPlanStep(int index)
{
    if (index < 0 || index >= plan_.steps.size()) {
        return;
    }

    PlanGenerator::Step &step = plan_.steps[index];
    StepEditDialog dialog(step.stepId, step.title, step.params, this);
    if (dialog.exec() != QDialog::Accepted) {
        return;
    }

    const QJsonObject next = dialog.params();
    const QString error = StepCatalog::validateParams(step.stepId, next);
    if (!error.isEmpty()) {
        QMessageBox::warning(this, tr("Invalid parameters"), error);
        return;
    }

    step.params = next;
    planUserOwned_ = true;
    refreshPlanUi();
}

void NeuroFlowPage::movePlanStep(int index, int delta)
{
    const int target = index + delta;
    if (index < 0 || index >= plan_.steps.size() || target < 0 || target >= plan_.steps.size()) {
        return;
    }
    plan_.steps.swapItemsAt(index, target);
    planUserOwned_ = true;
    refreshPlanUi();
}

void NeuroFlowPage::removePlanStep(int index)
{
    if (index < 0 || index >= plan_.steps.size()) {
        return;
    }

    const QString title = plan_.steps.at(index).title;
    const auto answer = QMessageBox::question(
        this,
        tr("Remove step"),
        tr("Remove “%1” from the plan?").arg(title),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);
    if (answer != QMessageBox::Yes) {
        return;
    }

    plan_.steps.removeAt(index);
    planUserOwned_ = true;
    refreshPlanUi();
}

void NeuroFlowPage::addPlanStep()
{
    const QVector<StepCatalog::StepDefinition> catalog = StepCatalog::all();
    if (catalog.isEmpty()) {
        QMessageBox::warning(this, tr("No steps"), tr("The step catalog is empty."));
        return;
    }

    QStringList labels;
    labels.reserve(catalog.size());
    for (const StepCatalog::StepDefinition &def : catalog) {
        labels << QStringLiteral("%1 (%2)").arg(def.title, def.id);
    }

    bool ok = false;
    const QString chosen = QInputDialog::getItem(
        this,
        tr("Add step"),
        tr("Choose a preprocessing step:"),
        labels,
        0,
        false,
        &ok);
    if (!ok || chosen.isEmpty()) {
        return;
    }

    const int chosenIndex = labels.indexOf(chosen);
    if (chosenIndex < 0 || chosenIndex >= catalog.size()) {
        return;
    }

    plan_.steps.append(makeCatalogStep(
        catalog.at(chosenIndex).id,
        tr("Added manually.")));
    planUserOwned_ = true;
    refreshPlanUi();
}

void NeuroFlowPage::savePlan()
{
    if (ProjectDir::instance().root().isEmpty()) {
        QMessageBox::warning(this, tr("No project folder"),
                             tr("Configure a project folder before saving plans."));
        return;
    }
    if (PlanGenerator::isEmpty(plan_)) {
        QMessageBox::warning(this, tr("Empty plan"), tr("Add at least one step before saving."));
        return;
    }

    QString preferredBase = QFileInfo(fullFileName_).completeBaseName();
    if (preferredBase.isEmpty()) {
        preferredBase = QStringLiteral("plan");
    } else {
        preferredBase += QStringLiteral("_plan");
    }

    const QString defaultPath = planPath_.isEmpty()
                                    ? PlanIo::suggestSavePath(preferredBase)
                                    : planPath_;
    const QString destination = QFileDialog::getSaveFileName(
        this,
        tr("Save plan"),
        defaultPath,
        PlanIo::fileFilters().join(QStringLiteral(";;")));
    if (destination.isEmpty()) {
        return;
    }

    QJsonObject metadata;
    if (!datasetPath_.isEmpty()) {
        metadata.insert(QStringLiteral("dataset_path"), datasetPath_);
    }
    if (!fullFileName_.isEmpty()) {
        metadata.insert(QStringLiteral("name"), preferredBase);
    }

    const PlanIo::Result result = PlanIo::save(plan_, destination, metadata);
    if (!result.ok) {
        QMessageBox::warning(this, tr("Save failed"), result.error);
        return;
    }

    planPath_ = result.path;
    refreshPlanUi();
    QMessageBox::information(
        this,
        tr("Plan saved"),
        tr("Saved to %1").arg(QDir::toNativeSeparators(result.path)));
}

void NeuroFlowPage::loadPlan()
{
    if (ProjectDir::instance().root().isEmpty()) {
        QMessageBox::warning(this, tr("No project folder"),
                             tr("Configure a project folder before loading plans."));
        return;
    }

    const QString source = QFileDialog::getOpenFileName(
        this,
        tr("Load plan"),
        ProjectDir::instance().plansDir(),
        PlanIo::fileFilters().join(QStringLiteral(";;")));
    if (source.isEmpty()) {
        return;
    }

    const PlanIo::Result result = PlanIo::load(source);
    if (!result.ok) {
        QMessageBox::warning(this, tr("Load failed"), result.error);
        return;
    }

    plan_ = result.plan;
    planPath_ = result.path;
    planUserOwned_ = true;
    setPlanReady(plan_);
}

void NeuroFlowPage::runPlan()
{
    if (ProjectDir::instance().root().isEmpty()) {
        QMessageBox::warning(this, tr("No project folder"),
                             tr("Configure a project folder before running plans."));
        return;
    }
    if (datasetPath_.isEmpty()) {
        QMessageBox::warning(this, tr("No recording"),
                             tr("Import a recording before running the plan."));
        return;
    }
    if (!ProjectDir::instance().contains(datasetPath_)) {
        QMessageBox::warning(this, tr("Invalid recording"),
                             tr("Recording is outside the project folder."));
        return;
    }
    if (PlanGenerator::isEmpty(plan_)) {
        QMessageBox::warning(this, tr("Empty plan"),
                             tr("Add at least one step before running."));
        return;
    }
    if (WorkerClient::workersRoot().isEmpty()) {
        QMessageBox::warning(this, tr("Worker missing"),
                             tr("NeuroFlow worker not found."));
        return;
    }
    if (workerClient_->isBusy()) {
        QMessageBox::warning(this, tr("Busy"), tr("A worker is already running."));
        return;
    }

    QString preferredBase = QFileInfo(fullFileName_).completeBaseName();
    if (preferredBase.isEmpty()) {
        preferredBase = QStringLiteral("run");
    }

    const RunIo::Paths paths = RunIo::suggestPaths(preferredBase);
    if (paths.outputPath.isEmpty() || paths.metadataPath.isEmpty()) {
        QMessageBox::warning(this, tr("Run failed"),
                             tr("Could not create a runs/ folder."));
        return;
    }

    runOutputPath_ = paths.outputPath;
    runMetadataPath_ = paths.metadataPath;

    setRunLoading();
    pendingOp_ = WorkerOp::Run;
    // ICA / long recordings can take a while; allow up to 30 minutes.
    workerClient_->startRequest(
        QStringLiteral("neuroflow"),
        QStringLiteral("run"),
        QJsonObject{
            {QStringLiteral("input_path"), datasetPath_},
            {QStringLiteral("output_path"), runOutputPath_},
            {QStringLiteral("plan"), PlanGenerator::toJson(plan_)},
        },
        30 * 60 * 1000);
}

void NeuroFlowPage::setRunIdle()
{
    runStatus_->setText(
        tr("Run the plan to write cleaned output under runs/. A run.json sidecar links "
           "the result back to this plan."));
    runSkeleton_->setVisible(false);
    runResult_->clear();
    runResult_->setVisible(false);
    runLog_->clear();
    runLog_->setVisible(false);
    cancelRunButton_->setVisible(false);
    updateRunActionsEnabled();
}

void NeuroFlowPage::setRunLoading()
{
    runStatus_->setText(tr("Starting run… ICA and long recordings can take a few minutes."));
    runSkeleton_->setVisible(true);
    runResult_->clear();
    runResult_->setVisible(false);
    runLog_->clear();
    runLog_->setVisible(false);
    runPlanButton_->setEnabled(false);
    cancelRunButton_->setVisible(true);
}

void NeuroFlowPage::setRunReady(const QJsonObject &result,
                                const QString &outputPath,
                                const QString &metaPath)
{
    const QString kind = result.value(QStringLiteral("output_kind")).toString(QStringLiteral("raw"));
    const int nSteps = result.value(QStringLiteral("n_steps")).toInt(plan_.steps.size());
    QStringList lines;
    lines << tr("Finished %n step(s).", nullptr, nSteps);
    lines << tr("Output (%1): %2")
                 .arg(kind, QDir::toNativeSeparators(outputPath));
    lines << tr("Metadata: %1").arg(QDir::toNativeSeparators(metaPath));
    if (result.contains(QStringLiteral("sfreq"))) {
        lines << tr("Sampling rate: %1")
                     .arg(formatHz(result.value(QStringLiteral("sfreq")).toDouble()));
    }
    if (result.contains(QStringLiteral("n_epochs"))) {
        lines << tr("Epochs: %1").arg(result.value(QStringLiteral("n_epochs")).toInt());
    } else if (result.contains(QStringLiteral("duration_sec"))) {
        lines << tr("Duration: %1")
                     .arg(formatDuration(result.value(QStringLiteral("duration_sec")).toDouble()));
    }
    const QJsonObject repro = result.value(QStringLiteral("reproducibility")).toObject();
    if (!repro.isEmpty()) {
        const int seed = repro.value(QStringLiteral("ica_random_state"))
                             .toInt(repro.value(QStringLiteral("seed")).toInt());
        const QJsonObject env = repro.value(QStringLiteral("environment")).toObject();
        const QString mne = env.value(QStringLiteral("mne")).toString(
            result.value(QStringLiteral("mne_version")).toString());
        if (seed > 0) {
            lines << tr("Repro seed (ICA): %1").arg(seed);
        }
        if (!mne.isEmpty()) {
            lines << tr("MNE: %1").arg(mne);
        }
    }

    runStatus_->setText(tr("Run complete."));
    runSkeleton_->setVisible(false);
    runResult_->setText(lines.join(QLatin1Char('\n')));
    runResult_->setVisible(true);
    cancelRunButton_->setVisible(false);
    updateRunActionsEnabled();
}

void NeuroFlowPage::setRunError(const QString &message)
{
    runStatus_->setText(message);
    runSkeleton_->setVisible(false);
    runResult_->clear();
    runResult_->setVisible(false);
    cancelRunButton_->setVisible(false);
    updateRunActionsEnabled();
}

void NeuroFlowPage::updateRunActionsEnabled()
{
    if (runPlanButton_ == nullptr) {
        return;
    }
    runPlanButton_->setEnabled(!datasetPath_.isEmpty() && !PlanGenerator::isEmpty(plan_)
                               && (workerClient_ == nullptr || !workerClient_->isBusy()));
}

PlanGenerator::Step NeuroFlowPage::makeCatalogStep(const QString &stepId, const QString &rationale)
{
    PlanGenerator::Step step;
    step.stepId = stepId;
    step.params = StepCatalog::defaultParams(stepId);
    step.rationale = rationale;
    if (const StepCatalog::StepDefinition *def = StepCatalog::find(stepId)) {
        step.title = def->title;
    } else {
        step.title = stepId;
    }
    return step;
}

QString NeuroFlowPage::formatStepParams(const QJsonObject &params)
{
    if (params.isEmpty()) {
        return {};
    }

    QStringList parts;
    const QStringList keys = params.keys();
    for (const QString &key : keys) {
        const QJsonValue value = params.value(key);
        QString rendered;
        if (value.isBool()) {
            rendered = value.toBool() ? QStringLiteral("true") : QStringLiteral("false");
        } else if (value.isDouble()) {
            const double number = value.toDouble();
            if (qAbs(number - qRound(number)) < 1e-9) {
                rendered = QString::number(qRound(number));
            } else {
                rendered = QString::number(number, 'g', 4);
            }
        } else if (value.isString()) {
            rendered = value.toString();
            if (rendered.isEmpty()) {
                continue;
            }
        } else {
            continue;
        }
        parts << QStringLiteral("%1=%2").arg(key, rendered);
    }
    return parts.join(QStringLiteral(" · "));
}

void NeuroFlowPage::populateFingerprintCard(const QJsonObject &result)
{
    const int nChannels = result.value(QStringLiteral("n_channels")).toInt();
    const double sfreq = result.value(QStringLiteral("sfreq")).toDouble();
    const double duration = result.value(QStringLiteral("duration_sec")).toDouble();
    const QString montage = result.value(QStringLiteral("montage_hint")).toString();

    fpChannelsValue_->setText(tr("%n channel(s)", nullptr, nChannels));
    fpSfreqValue_->setText(formatHz(sfreq));
    fpDurationValue_->setText(formatDuration(duration));
    fpMontageValue_->setText(montage.isEmpty() ? tr("Unknown") : montage);

    const QString highpass = formatOptionalHz(result.value(QStringLiteral("highpass")));
    const QString lowpass = formatOptionalHz(result.value(QStringLiteral("lowpass")));
    if (highpass == QLatin1String("—") && lowpass == QLatin1String("—")) {
        fpFiltersValue_->setText(tr("Not reported"));
    } else {
        fpFiltersValue_->setText(tr("%1 – %2").arg(highpass, lowpass));
    }

    const QJsonArray names = result.value(QStringLiteral("ch_names")).toArray();
    QStringList preview;
    constexpr int kPreviewLimit = 12;
    for (int i = 0; i < names.size() && i < kPreviewLimit; ++i) {
        preview << names.at(i).toString();
    }
    QString channelText = preview.join(QStringLiteral(", "));
    if (names.size() > kPreviewLimit) {
        channelText += tr(", +%1 more").arg(names.size() - kPreviewLimit);
    }
    if (channelText.isEmpty()) {
        channelText = tr("None");
    }
    fpChannelNames_->setText(channelText);

    QStringList allNames;
    allNames.reserve(names.size());
    for (const QJsonValue &value : names) {
        allNames << value.toString();
    }
    fpChannelNames_->setToolTip(allNames.join(QStringLiteral(", ")));
}

void NeuroFlowPage::refreshIcons()
{
    const Theme &theme = Theme::instance();
    const QIcon fileIcon =
        icons::icon(icons::Glyph::File, theme.mutedTextColor(), theme.textColor());

    if (emptyIconLabel_ != nullptr) {
        emptyIconLabel_->setPixmap(fileIcon.pixmap(QSize(26, 26), QIcon::Normal));
    }
    if (fileIconLabel_ != nullptr) {
        fileIconLabel_->setPixmap(fileIcon.pixmap(QSize(22, 22), QIcon::Normal));
    }
}

void NeuroFlowPage::updateElidedTexts()
{
    if (fileNameLabel_ == nullptr || recordingStack_->currentIndex() != 1) {
        return;
    }

    // Ensure labels have a real width before eliding.
    fileNameLabel_->setText(fullFileName_);
    filePathLabel_->setText(fullFilePath_);

    const int nameWidth = qMax(48, fileNameLabel_->width());
    const int pathWidth = qMax(48, filePathLabel_->width());

    const QFontMetrics nameMetrics(fileNameLabel_->font());
    fileNameLabel_->setText(nameMetrics.elidedText(fullFileName_, Qt::ElideMiddle, nameWidth));
    fileNameLabel_->setToolTip(fullFileName_);

    const QFontMetrics pathMetrics(filePathLabel_->font());
    filePathLabel_->setText(pathMetrics.elidedText(fullFilePath_, Qt::ElideMiddle, pathWidth));
    filePathLabel_->setToolTip(fullFilePath_);
}

QString NeuroFlowPage::formatFileSize(qint64 bytes)
{
    if (bytes < 1024) {
        return tr("%1 B").arg(bytes);
    }
    if (bytes < 1024 * 1024) {
        return tr("%1 KB").arg(bytes / 1024.0, 0, 'f', 1);
    }
    if (bytes < 1024LL * 1024 * 1024) {
        return tr("%1 MB").arg(bytes / (1024.0 * 1024.0), 0, 'f', 1);
    }
    return tr("%1 GB").arg(bytes / (1024.0 * 1024.0 * 1024.0), 0, 'f', 2);
}

QString NeuroFlowPage::formatDuration(double seconds)
{
    if (seconds < 0 || seconds != seconds) {
        return tr("—");
    }
    if (seconds < 60.0) {
        return tr("%1 s").arg(seconds, 0, 'f', seconds < 10.0 ? 2 : 1);
    }
    const int totalSec = static_cast<int>(seconds + 0.5);
    const int hours = totalSec / 3600;
    const int minutes = (totalSec % 3600) / 60;
    const int secs = totalSec % 60;
    if (hours > 0) {
        return tr("%1 h %2 m").arg(hours).arg(minutes);
    }
    if (secs == 0) {
        return tr("%1 min").arg(minutes);
    }
    return tr("%1 min %2 s").arg(minutes).arg(secs);
}

QString NeuroFlowPage::formatHz(double hz)
{
    if (hz <= 0.0 || hz != hz) {
        return tr("—");
    }
    if (qAbs(hz - qRound(hz)) < 1e-6) {
        return tr("%1 Hz").arg(qRound(hz));
    }
    return tr("%1 Hz").arg(hz, 0, 'f', 2);
}

QString NeuroFlowPage::formatOptionalHz(const QJsonValue &value)
{
    if (value.isNull() || !value.isDouble()) {
        return QStringLiteral("—");
    }
    return formatHz(value.toDouble());
}

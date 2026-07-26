#include "modules/neuroflow/neuroflowpage.hpp"

#include "core/datasetimport.hpp"
#include "core/plangenerator.hpp"
#include "core/projectdir.hpp"
#include "core/theme.hpp"
#include "core/workerclient.hpp"
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

    auto *chooseButton = new QPushButton(tr("Choose file…"), emptyPanel);
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
    planLayout->addWidget(planStatus_);

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
    layout->addStretch(1);

    scroll->setWidget(content);
    rootLayout->addWidget(scroll);

    connect(&Theme::instance(), &Theme::changed, this, &NeuroFlowPage::refreshIcons);
    connect(workerClient_,
            &WorkerClient::finished,
            this,
            &NeuroFlowPage::onFingerprintFinished);
    refreshIcons();
    setFingerprintIdle();
    setPlanIdle();
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
    cancelFingerprint();
    datasetPath_.clear();
    fullFileName_.clear();
    fullFilePath_.clear();
    fingerprint_ = {};
    clearPlan();
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
}

void NeuroFlowPage::setDatasetPath(const QString &path, bool copied)
{
    cancelFingerprint();

    datasetPath_ = path;
    fingerprint_ = {};
    clearPlan();
    setPlanIdle();
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

    setFingerprintLoading();
    workerClient_->startRequest(
        QStringLiteral("neuroflow"),
        QStringLiteral("fingerprint"),
        QJsonObject{{QStringLiteral("path"), datasetPath_}},
        60000);
}

void NeuroFlowPage::cancelFingerprint()
{
    if (workerClient_ != nullptr && workerClient_->isBusy()) {
        workerClient_->cancel();
    }
}

void NeuroFlowPage::onFingerprintFinished(bool ok,
                                          const QJsonObject &result,
                                          const QString &errorCode,
                                          const QString &errorMessage)
{
    if (errorCode == QLatin1String("cancelled")) {
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
    clearPlan();
    setPlanIdle();
    fingerprintStatus_->setText(tr("Reading recording…"));
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
    regeneratePlan();
}

void NeuroFlowPage::setFingerprintError(const QString &message)
{
    fingerprint_ = {};
    clearPlan();
    setPlanIdle();
    fingerprintStatus_->setText(message);
    fingerprintStatus_->setVisible(true);
    fingerprintSkeleton_->setVisible(false);
    fingerprintCard_->setVisible(false);
}

void NeuroFlowPage::regeneratePlan()
{
    plan_ = PlanGenerator::fromFingerprint(fingerprint_);
    if (PlanGenerator::isEmpty(plan_)) {
        setPlanIdle();
        return;
    }
    setPlanReady(plan_);
}

void NeuroFlowPage::clearPlan()
{
    plan_ = {};
}

void NeuroFlowPage::setPlanIdle()
{
    planStatus_->setText(
        tr("A default step plan appears here after the recording is fingerprinted."));
}

void NeuroFlowPage::setPlanReady(const PlanGenerator::Plan &plan)
{
    QStringList titles;
    titles.reserve(plan.steps.size());
    for (const PlanGenerator::Step &step : plan.steps) {
        titles << step.title;
    }

    planStatus_->setText(
        tr("Generated %n step(s): %1", nullptr, plan.steps.size())
            .arg(titles.join(QStringLiteral(" → "))));
    planStatus_->setToolTip(QString::fromUtf8(
        QJsonDocument(PlanGenerator::toJson(plan)).toJson(QJsonDocument::Indented)));
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

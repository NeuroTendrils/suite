#include "modules/neurostudio/neurostudiopage.hpp"

#include "core/projectdir.hpp"
#include "core/studiodataset.hpp"
#include "core/studioexportio.hpp"
#include "core/studiotrainio.hpp"
#include "core/templatecatalog.hpp"
#include "core/templaterecommender.hpp"
#include "core/theme.hpp"
#include "core/workerclient.hpp"
#include "modules/neurostudio/templateeditdialog.hpp"
#include "widgets/icons.hpp"
#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QCheckBox>
#include <QComboBox>
#include <QDir>
#include <QDoubleSpinBox>
#include <QFileDialog>
#include <QFileInfo>
#include <QFontMetrics>
#include <QFormLayout>
#include <QFrame>
#include <QGridLayout>
#include <QHash>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
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

NeuroStudioPage::NeuroStudioPage(QWidget *parent)
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
        tr("NeuroStudio"),
        tr("Train models on cleaned local data from NeuroFlow runs."),
        content);

    auto *datasetLabel = new QLabel(tr("Training data"), content);
    datasetLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(datasetLabel);

    datasetStack_ = new QStackedWidget(content);
    makeFlexible(datasetStack_);
    datasetStack_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    auto *emptyPanel = makePanel(QStringLiteral("emptyPanel"), datasetStack_);
    auto *emptyLayout = new QVBoxLayout(emptyPanel);
    emptyLayout->setContentsMargins(16, 18, 16, 18);
    emptyLayout->setSpacing(0);

    emptyIconLabel_ = new QLabel(emptyPanel);
    emptyIconLabel_->setAlignment(Qt::AlignHCenter | Qt::AlignVCenter);
    emptyIconLabel_->setFixedHeight(28);
    makeFlexible(emptyIconLabel_);

    auto *emptyTitle = new QLabel(tr("Choose training data"), emptyPanel);
    emptyTitle->setObjectName(QStringLiteral("emptyPanelTitle"));
    emptyTitle->setAlignment(Qt::AlignHCenter | Qt::AlignVCenter);
    emptyTitle->setWordWrap(true);
    makeFlexible(emptyTitle);

    emptyHint_ = new QLabel(
        tr("Prefer a NeuroFlow run (runs/…/cleaned.fif). Paths must stay inside the project."),
        emptyPanel);
    emptyHint_->setObjectName(QStringLiteral("emptyPanelHint"));
    emptyHint_->setAlignment(Qt::AlignHCenter | Qt::AlignTop);
    emptyHint_->setWordWrap(true);
    makeFlexible(emptyHint_);

    auto *chooseButton = new QPushButton(tr("Choose data…"), emptyPanel);
    chooseButton->setObjectName(QStringLiteral("primaryButton"));
    chooseButton->setCursor(Qt::PointingHandCursor);
    chooseButton->setAutoDefault(false);
    connect(chooseButton, &QPushButton::clicked, this, &NeuroStudioPage::chooseDataset);

    auto *chooseRow = new QWidget(emptyPanel);
    makeFlexible(chooseRow);
    auto *chooseRowLayout = new QHBoxLayout(chooseRow);
    chooseRowLayout->setContentsMargins(0, 0, 0, 0);
    chooseRowLayout->addStretch();
    chooseRowLayout->addWidget(chooseButton);
    chooseRowLayout->addStretch();

    emptyLayout->addWidget(emptyIconLabel_);
    emptyLayout->addSpacing(8);
    emptyLayout->addWidget(emptyTitle);
    emptyLayout->addSpacing(4);
    emptyLayout->addWidget(emptyHint_);
    emptyLayout->addSpacing(12);
    emptyLayout->addWidget(chooseRow);

    auto *filePanel = makePanel(QStringLiteral("filePanel"), datasetStack_);
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

    auto *textCol = new QWidget(topRow);
    makeFlexible(textCol);
    auto *textLayout = new QVBoxLayout(textCol);
    textLayout->setContentsMargins(0, 0, 0, 0);
    textLayout->setSpacing(2);

    fileNameLabel_ = new QLabel(textCol);
    fileNameLabel_->setObjectName(QStringLiteral("fileNameLabel"));
    makeFlexible(fileNameLabel_);

    fileMetaLabel_ = new QLabel(textCol);
    fileMetaLabel_->setObjectName(QStringLiteral("upcomingCaption"));
    makeFlexible(fileMetaLabel_);

    textLayout->addWidget(fileNameLabel_);
    textLayout->addWidget(fileMetaLabel_);

    fileBadge_ = new QLabel(topRow);
    fileBadge_->setObjectName(QStringLiteral("fileBadge"));
    fileBadge_->setAlignment(Qt::AlignCenter);
    fileBadge_->setVisible(false);

    topLayout->addWidget(fileIconLabel_, 0, Qt::AlignTop);
    topLayout->addWidget(textCol, 1);
    topLayout->addWidget(fileBadge_, 0, Qt::AlignTop);

    filePathLabel_ = new QLabel(filePanel);
    filePathLabel_->setObjectName(QStringLiteral("upcomingCaption"));
    filePathLabel_->setWordWrap(false);
    makeFlexible(filePathLabel_);

    changeButton_ = new QPushButton(tr("Change…"), filePanel);
    changeButton_->setObjectName(QStringLiteral("secondaryButton"));
    changeButton_->setCursor(Qt::PointingHandCursor);
    changeButton_->setAutoDefault(false);
    connect(changeButton_, &QPushButton::clicked, this, &NeuroStudioPage::chooseDataset);

    clearButton_ = new QPushButton(tr("Clear"), filePanel);
    clearButton_->setObjectName(QStringLiteral("secondaryButton"));
    clearButton_->setCursor(Qt::PointingHandCursor);
    clearButton_->setAutoDefault(false);
    connect(clearButton_, &QPushButton::clicked, this, &NeuroStudioPage::clearDataset);

    auto *actions = new QWidget(filePanel);
    makeFlexible(actions);
    auto *actionsLayout = new QHBoxLayout(actions);
    actionsLayout->setContentsMargins(0, 0, 0, 0);
    actionsLayout->setSpacing(8);
    actionsLayout->addWidget(changeButton_, 0, Qt::AlignLeft);
    actionsLayout->addWidget(clearButton_, 0, Qt::AlignLeft);
    actionsLayout->addStretch(1);

    fileLayout->addWidget(topRow);
    fileLayout->addWidget(filePathLabel_);
    fileLayout->addWidget(actions);

    datasetStack_->addWidget(emptyPanel);
    datasetStack_->addWidget(filePanel);

    auto *templatesLabel = new QLabel(tr("Templates"), content);
    templatesLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(templatesLabel);

    auto *templatesPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *templatesLayout = new QVBoxLayout(templatesPanel);
    templatesLayout->setContentsMargins(12, 12, 12, 12);
    templatesLayout->setSpacing(8);

    templatesStatus_ = new QLabel(templatesPanel);
    templatesStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    templatesStatus_->setWordWrap(true);
    makeFlexible(templatesStatus_);

    templateListHost_ = new QWidget(templatesPanel);
    makeFlexible(templateListHost_);
    templateListLayout_ = new QVBoxLayout(templateListHost_);
    templateListLayout_->setContentsMargins(0, 0, 0, 0);
    templateListLayout_->setSpacing(8);

    templatesLayout->addWidget(templatesStatus_);
    templatesLayout->addWidget(templateListHost_);

    auto *tuneLabel = new QLabel(tr("Tune"), content);
    tuneLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(tuneLabel);

    auto *tunePanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *tuneLayout = new QVBoxLayout(tunePanel);
    tuneLayout->setContentsMargins(12, 12, 12, 12);
    tuneLayout->setSpacing(8);

    tuneStatus_ = new QLabel(tunePanel);
    tuneStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    tuneStatus_->setWordWrap(true);
    makeFlexible(tuneStatus_);

    tuneFormHost_ = new QWidget(tunePanel);
    makeFlexible(tuneFormHost_);
    tuneForm_ = new QFormLayout(tuneFormHost_);
    tuneForm_->setContentsMargins(0, 0, 0, 0);
    tuneForm_->setHorizontalSpacing(12);
    tuneForm_->setVerticalSpacing(10);
    tuneForm_->setFieldGrowthPolicy(QFormLayout::ExpandingFieldsGrow);

    tuneError_ = new QLabel(tunePanel);
    tuneError_->setObjectName(QStringLiteral("stepEditError"));
    tuneError_->setWordWrap(true);
    tuneError_->setVisible(false);
    makeFlexible(tuneError_);

    resetTuneButton_ = new QPushButton(tr("Reset to defaults"), tunePanel);
    resetTuneButton_->setObjectName(QStringLiteral("secondaryButton"));
    resetTuneButton_->setCursor(Qt::PointingHandCursor);
    resetTuneButton_->setAutoDefault(false);
    connect(resetTuneButton_, &QPushButton::clicked, this, &NeuroStudioPage::resetTuneDefaults);

    auto *tuneActions = new QWidget(tunePanel);
    makeFlexible(tuneActions);
    auto *tuneActionsLayout = new QHBoxLayout(tuneActions);
    tuneActionsLayout->setContentsMargins(0, 0, 0, 0);
    tuneActionsLayout->setSpacing(8);
    tuneActionsLayout->addWidget(resetTuneButton_, 0, Qt::AlignLeft);
    tuneActionsLayout->addStretch(1);

    auto *autoTuneNote = new QLabel(
        tr("Manual controls only — no auto hyperparameter search in this phase."),
        tunePanel);
    autoTuneNote->setObjectName(QStringLiteral("upcomingCaption"));
    autoTuneNote->setWordWrap(true);
    makeFlexible(autoTuneNote);

    tuneLayout->addWidget(tuneStatus_);
    tuneLayout->addWidget(tuneFormHost_);
    tuneLayout->addWidget(tuneError_);
    tuneLayout->addWidget(tuneActions);
    tuneLayout->addWidget(autoTuneNote);

    auto *trainLabel = new QLabel(tr("Train"), content);
    trainLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(trainLabel);

    auto *trainPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *trainLayout = new QVBoxLayout(trainPanel);
    trainLayout->setContentsMargins(12, 12, 12, 12);
    trainLayout->setSpacing(8);

    trainStatus_ = new QLabel(trainPanel);
    trainStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    trainStatus_->setWordWrap(true);
    makeFlexible(trainStatus_);

    trainSkeleton_ = new SkeletonLoader(trainPanel);
    trainSkeleton_->addBlock(0.9, 14, 6);
    trainSkeleton_->addBlock(0.7, 14, 6);
    trainSkeleton_->addBlock(0.55, 14, 6);
    trainSkeleton_->setVisible(false);

    liveMetrics_ = new QLabel(trainPanel);
    liveMetrics_->setObjectName(QStringLiteral("planStepTitle"));
    liveMetrics_->setWordWrap(true);
    liveMetrics_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    liveMetrics_->setVisible(false);
    makeFlexible(liveMetrics_);

    finalMetrics_ = new QLabel(trainPanel);
    finalMetrics_->setObjectName(QStringLiteral("upcomingCaption"));
    finalMetrics_->setWordWrap(true);
    finalMetrics_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    finalMetrics_->setVisible(false);
    makeFlexible(finalMetrics_);

    confusionHost_ = new QWidget(trainPanel);
    makeFlexible(confusionHost_);
    confusionLayout_ = new QVBoxLayout(confusionHost_);
    confusionLayout_->setContentsMargins(0, 0, 0, 0);
    confusionLayout_->setSpacing(6);
    confusionHost_->setVisible(false);

    artifactsLabel_ = new QLabel(trainPanel);
    artifactsLabel_->setObjectName(QStringLiteral("upcomingCaption"));
    artifactsLabel_->setWordWrap(true);
    artifactsLabel_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    artifactsLabel_->setVisible(false);
    makeFlexible(artifactsLabel_);

    trainLog_ = new QLabel(trainPanel);
    trainLog_->setObjectName(QStringLiteral("upcomingCaption"));
    trainLog_->setWordWrap(true);
    trainLog_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    trainLog_->setVisible(false);
    makeFlexible(trainLog_);

    auto *deviceRow = new QWidget(trainPanel);
    makeFlexible(deviceRow);
    auto *deviceRowLayout = new QHBoxLayout(deviceRow);
    deviceRowLayout->setContentsMargins(0, 0, 0, 0);
    deviceRowLayout->setSpacing(8);
    auto *deviceLabel = new QLabel(tr("Device"), deviceRow);
    deviceLabel->setObjectName(QStringLiteral("upcomingCaption"));
    deviceCombo_ = new QComboBox(deviceRow);
    deviceCombo_->addItem(tr("Auto"), QStringLiteral("auto"));
    deviceCombo_->addItem(tr("CPU"), QStringLiteral("cpu"));
    deviceCombo_->addItem(tr("CUDA (NVIDIA)"), QStringLiteral("cuda"));
    deviceCombo_->addItem(tr("MPS (Apple)"), QStringLiteral("mps"));
    deviceCombo_->setCurrentIndex(0);
    deviceRowLayout->addWidget(deviceLabel, 0);
    deviceRowLayout->addWidget(deviceCombo_, 0);
    deviceRowLayout->addStretch(1);

    trainButton_ = new QPushButton(tr("Train"), trainPanel);
    trainButton_->setObjectName(QStringLiteral("primaryButton"));
    trainButton_->setCursor(Qt::PointingHandCursor);
    trainButton_->setAutoDefault(false);
    connect(trainButton_, &QPushButton::clicked, this, &NeuroStudioPage::startTraining);

    cancelTrainButton_ = new QPushButton(tr("Cancel"), trainPanel);
    cancelTrainButton_->setObjectName(QStringLiteral("secondaryButton"));
    cancelTrainButton_->setCursor(Qt::PointingHandCursor);
    cancelTrainButton_->setAutoDefault(false);
    cancelTrainButton_->setVisible(false);
    connect(cancelTrainButton_, &QPushButton::clicked, this, &NeuroStudioPage::cancelTraining);

    auto *trainActions = new QWidget(trainPanel);
    makeFlexible(trainActions);
    auto *trainActionsLayout = new QHBoxLayout(trainActions);
    trainActionsLayout->setContentsMargins(0, 0, 0, 0);
    trainActionsLayout->setSpacing(8);
    trainActionsLayout->addWidget(trainButton_, 0, Qt::AlignLeft);
    trainActionsLayout->addWidget(cancelTrainButton_, 0, Qt::AlignLeft);
    trainActionsLayout->addStretch(1);

    trainLayout->addWidget(trainStatus_);
    trainLayout->addWidget(deviceRow);
    trainLayout->addWidget(trainSkeleton_);
    trainLayout->addWidget(liveMetrics_);
    trainLayout->addWidget(finalMetrics_);
    trainLayout->addWidget(confusionHost_);
    trainLayout->addWidget(artifactsLabel_);
    trainLayout->addWidget(trainLog_);
    trainLayout->addWidget(trainActions);

    auto *exportLabel = new QLabel(tr("Export"), content);
    exportLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(exportLabel);

    auto *exportPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *exportLayout = new QVBoxLayout(exportPanel);
    exportLayout->setContentsMargins(12, 12, 12, 12);
    exportLayout->setSpacing(8);

    exportStatus_ = new QLabel(exportPanel);
    exportStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    exportStatus_->setWordWrap(true);
    makeFlexible(exportStatus_);

    exportSkeleton_ = new SkeletonLoader(exportPanel);
    exportSkeleton_->addBlock(0.85, 14, 6);
    exportSkeleton_->addBlock(0.6, 14, 6);
    exportSkeleton_->setVisible(false);

    exportResult_ = new QLabel(exportPanel);
    exportResult_->setObjectName(QStringLiteral("upcomingCaption"));
    exportResult_->setWordWrap(true);
    exportResult_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    exportResult_->setVisible(false);
    makeFlexible(exportResult_);

    auto *formatRow = new QWidget(exportPanel);
    makeFlexible(formatRow);
    auto *formatRowLayout = new QHBoxLayout(formatRow);
    formatRowLayout->setContentsMargins(0, 0, 0, 0);
    formatRowLayout->setSpacing(8);
    auto *formatLabel = new QLabel(tr("Format"), formatRow);
    formatLabel->setObjectName(QStringLiteral("upcomingCaption"));
    exportFormatCombo_ = new QComboBox(formatRow);
    exportFormatCombo_->addItem(tr("PyTorch (.pt)"), QStringLiteral("pt"));
    exportFormatCombo_->addItem(tr("TorchScript"), QStringLiteral("torchscript"));
    exportFormatCombo_->addItem(tr("ONNX"), QStringLiteral("onnx"));
    exportFormatCombo_->addItem(tr("SafeTensors"), QStringLiteral("safetensors"));
    exportFormatCombo_->setCurrentIndex(0);
    formatRowLayout->addWidget(formatLabel, 0);
    formatRowLayout->addWidget(exportFormatCombo_, 0);
    formatRowLayout->addStretch(1);

    exportButton_ = new QPushButton(tr("Export"), exportPanel);
    exportButton_->setObjectName(QStringLiteral("primaryButton"));
    exportButton_->setCursor(Qt::PointingHandCursor);
    exportButton_->setAutoDefault(false);
    connect(exportButton_, &QPushButton::clicked, this, &NeuroStudioPage::startExport);

    cancelExportButton_ = new QPushButton(tr("Cancel"), exportPanel);
    cancelExportButton_->setObjectName(QStringLiteral("secondaryButton"));
    cancelExportButton_->setCursor(Qt::PointingHandCursor);
    cancelExportButton_->setAutoDefault(false);
    cancelExportButton_->setVisible(false);
    connect(cancelExportButton_, &QPushButton::clicked, this, &NeuroStudioPage::cancelExport);

    publishPlaceholderButton_ = new QPushButton(tr("Publish to cloud…"), exportPanel);
    publishPlaceholderButton_->setObjectName(QStringLiteral("secondaryButton"));
    publishPlaceholderButton_->setCursor(Qt::PointingHandCursor);
    publishPlaceholderButton_->setAutoDefault(false);
    publishPlaceholderButton_->setEnabled(false);
    publishPlaceholderButton_->setToolTip(
        tr("Cloud publish is not available yet — local models stay in models/."));
    connect(publishPlaceholderButton_, &QPushButton::clicked, this, [this]() {
        QMessageBox::information(
            this,
            tr("Cloud publish"),
            tr("Cloud publish is a placeholder for a later release. Exported models remain "
               "local under models/ and appear in Hub."));
    });

    auto *exportActions = new QWidget(exportPanel);
    makeFlexible(exportActions);
    auto *exportActionsLayout = new QHBoxLayout(exportActions);
    exportActionsLayout->setContentsMargins(0, 0, 0, 0);
    exportActionsLayout->setSpacing(8);
    exportActionsLayout->addWidget(exportButton_, 0, Qt::AlignLeft);
    exportActionsLayout->addWidget(cancelExportButton_, 0, Qt::AlignLeft);
    exportActionsLayout->addWidget(publishPlaceholderButton_, 0, Qt::AlignLeft);
    exportActionsLayout->addStretch(1);

    auto *exportNote = new QLabel(
        tr("Exports land in models/ with a model.json sidecar and show up in Hub."),
        exportPanel);
    exportNote->setObjectName(QStringLiteral("upcomingCaption"));
    exportNote->setWordWrap(true);
    makeFlexible(exportNote);

    exportLayout->addWidget(exportStatus_);
    exportLayout->addWidget(formatRow);
    exportLayout->addWidget(exportSkeleton_);
    exportLayout->addWidget(exportResult_);
    exportLayout->addWidget(exportActions);
    exportLayout->addWidget(exportNote);

    layout->addWidget(header);
    layout->addSpacing(16);
    layout->addWidget(datasetLabel);
    layout->addSpacing(6);
    layout->addWidget(datasetStack_);
    layout->addSpacing(16);
    layout->addWidget(templatesLabel);
    layout->addSpacing(6);
    layout->addWidget(templatesPanel);
    layout->addSpacing(16);
    layout->addWidget(tuneLabel);
    layout->addSpacing(6);
    layout->addWidget(tunePanel);
    layout->addSpacing(16);
    layout->addWidget(trainLabel);
    layout->addSpacing(6);
    layout->addWidget(trainPanel);
    layout->addSpacing(16);
    layout->addWidget(exportLabel);
    layout->addSpacing(6);
    layout->addWidget(exportPanel);
    layout->addStretch(1);

    scroll->setWidget(content);
    rootLayout->addWidget(scroll);

    connect(&Theme::instance(), &Theme::changed, this, &NeuroStudioPage::refreshIcons);
    connect(workerClient_, &WorkerClient::finished, this, &NeuroStudioPage::onWorkerFinished);
    connect(workerClient_, &WorkerClient::eventReceived, this, &NeuroStudioPage::onWorkerEvent);
    connect(workerClient_, &WorkerClient::logMessage, this, &NeuroStudioPage::onWorkerLog);
    refreshIcons();
    setDatasetIdle();
    refreshRecommendation();
    setTrainIdle();
    setExportIdle();
}

QString NeuroStudioPage::currentDatasetPath() const
{
    return datasetPath_;
}

QString NeuroStudioPage::currentTemplateId() const
{
    return selectedTemplateId_;
}

QJsonObject NeuroStudioPage::currentTemplateConfig() const
{
    return configFor(selectedTemplateId_);
}

void NeuroStudioPage::resizeEvent(QResizeEvent *event)
{
    QWidget::resizeEvent(event);
    updateElidedTexts();
}

void NeuroStudioPage::chooseDataset()
{
    if (ProjectDir::instance().root().isEmpty()) {
        QMessageBox::warning(this, tr("No project folder"),
                             tr("Configure a project folder before choosing training data."));
        return;
    }

    const QString source = QFileDialog::getOpenFileName(
        this,
        tr("Choose training data"),
        StudioDataset::preferredStartDir(),
        StudioDataset::fileFilters().join(QStringLiteral(";;")));
    if (source.isEmpty()) {
        return;
    }

    const StudioDataset::Result result = StudioDataset::selectPath(source);
    if (!result.ok) {
        QMessageBox::warning(this, tr("Invalid data"), result.error);
        return;
    }

    setDatasetPath(result.path, result.kind);
    updateTrainActionsEnabled();
}

void NeuroStudioPage::clearDataset()
{
    datasetPath_.clear();
    fullFileName_.clear();
    fullFilePath_.clear();
    datasetKind_.clear();
    fileNameLabel_->clear();
    fileMetaLabel_->clear();
    filePathLabel_->clear();
    filePathLabel_->setToolTip(QString());
    fileNameLabel_->setToolTip(QString());
    fileBadge_->clear();
    fileBadge_->setVisible(false);
    setDatasetIdle();
    refreshRecommendation();
    updateTrainActionsEnabled();
}

void NeuroStudioPage::setDatasetPath(const QString &path, const QString &kind)
{
    datasetPath_ = path;
    datasetKind_ = kind;
    const QFileInfo info(path);

    fullFileName_ = info.fileName();
    fullFilePath_ = QDir::toNativeSeparators(path);

    fileMetaLabel_->setText(
        tr("%1 · %2").arg(formatFileSize(info.size()), kindLabel(kind)));

    const QString suffix = info.suffix().toUpper();
    if (!suffix.isEmpty()) {
        fileBadge_->setText(suffix);
        fileBadge_->setVisible(true);
    } else {
        fileBadge_->setVisible(false);
    }

    datasetStack_->setCurrentIndex(1);
    refreshIcons();
    updateElidedTexts();
    refreshRecommendation();
    updateTrainActionsEnabled();
}

void NeuroStudioPage::setDatasetIdle()
{
    datasetStack_->setCurrentIndex(0);
}

void NeuroStudioPage::refreshRecommendation()
{
    suggestedTemplateId_.clear();

    if (datasetPath_.isEmpty()) {
        templatesStatus_->setText(
            tr("%n template(s) available. Choose training data to rank suggestions, then Select / "
               "Configure.",
               nullptr,
               TemplateCatalog::all().size()));
        if (selectedTemplateId_.isEmpty() && !TemplateCatalog::ids().isEmpty()) {
            selectedTemplateId_ = TemplateCatalog::ids().first();
        }
        rebuildTemplateList();
        rebuildTuneForm();
        updateTrainActionsEnabled();
        return;
    }

    const TemplateRecommender::Result rec =
        TemplateRecommender::recommend(datasetPath_, datasetKind_);
    if (!rec.ranked.isEmpty()) {
        suggestedTemplateId_ = rec.ranked.first().templateId;
        // Adopt the suggestion when nothing is selected yet, or the prior
        // selection was only the previous suggestion.
        if (selectedTemplateId_.isEmpty()
            || selectedTemplateId_ == suggestedTemplateId_
            || !TemplateCatalog::find(selectedTemplateId_)) {
            selectedTemplateId_ = suggestedTemplateId_;
        }
    }
    templatesStatus_->setText(rec.summary);
    rebuildTemplateList();
    rebuildTuneForm();
    updateTrainActionsEnabled();
}

void NeuroStudioPage::rebuildTemplateList()
{
    while (QLayoutItem *item = templateListLayout_->takeAt(0)) {
        if (QWidget *widget = item->widget()) {
            widget->deleteLater();
        }
        delete item;
    }

    TemplateRecommender::Result rec;
    if (!datasetPath_.isEmpty()) {
        rec = TemplateRecommender::recommend(datasetPath_, datasetKind_);
    }

    QVector<TemplateCatalog::TemplateDefinition> order = TemplateCatalog::all();
    if (!rec.ranked.isEmpty()) {
        order.clear();
        for (const TemplateRecommender::Suggestion &suggestion : rec.ranked) {
            if (const TemplateCatalog::TemplateDefinition *def =
                    TemplateCatalog::find(suggestion.templateId)) {
                order.append(*def);
            }
        }
    }

    QHash<QString, QString> rationales;
    for (const TemplateRecommender::Suggestion &suggestion : rec.ranked) {
        rationales.insert(suggestion.templateId, suggestion.rationale);
    }

    for (const TemplateCatalog::TemplateDefinition &item : order) {
        auto *row = new QFrame(templateListHost_);
        row->setObjectName(QStringLiteral("planStepRow"));
        row->setFrameShape(QFrame::NoFrame);
        makeFlexible(row);
        auto *rowLayout = new QVBoxLayout(row);
        rowLayout->setContentsMargins(12, 10, 12, 10);
        rowLayout->setSpacing(6);

        auto *header = new QWidget(row);
        makeFlexible(header);
        auto *headerLayout = new QHBoxLayout(header);
        headerLayout->setContentsMargins(0, 0, 0, 0);
        headerLayout->setSpacing(8);

        const bool suggested = !suggestedTemplateId_.isEmpty()
                               && item.id == suggestedTemplateId_;
        const bool selected = !selectedTemplateId_.isEmpty() && item.id == selectedTemplateId_;

        QString titleText = item.title;
        if (selected && suggested) {
            titleText = tr("Selected · Suggested · %1").arg(item.title);
        } else if (selected) {
            titleText = tr("Selected · %1").arg(item.title);
        } else if (suggested) {
            titleText = tr("Suggested · %1").arg(item.title);
        }

        auto *title = new QLabel(titleText, header);
        title->setObjectName(QStringLiteral("planStepTitle"));
        makeFlexible(title);

        auto *selectButton = new QPushButton(selected ? tr("Selected") : tr("Select"), header);
        selectButton->setObjectName(QStringLiteral("planStepButton"));
        selectButton->setCursor(Qt::PointingHandCursor);
        selectButton->setAutoDefault(false);
        selectButton->setEnabled(!selected);
        connect(selectButton, &QPushButton::clicked, this, [this, id = item.id]() {
            selectTemplate(id);
        });

        auto *configureButton = new QPushButton(tr("Configure"), header);
        configureButton->setObjectName(QStringLiteral("planStepButton"));
        configureButton->setCursor(Qt::PointingHandCursor);
        configureButton->setAutoDefault(false);
        connect(configureButton, &QPushButton::clicked, this, [this, id = item.id]() {
            configureTemplate(id);
        });

        headerLayout->addWidget(title, 1, Qt::AlignVCenter);
        headerLayout->addWidget(selectButton, 0, Qt::AlignVCenter);
        headerLayout->addWidget(configureButton, 0, Qt::AlignVCenter);

        auto *meta = new QLabel(
            tr("%1 · %2 · %3").arg(item.id, item.task, item.modelFamily), row);
        meta->setObjectName(QStringLiteral("planStepMeta"));
        meta->setWordWrap(true);
        makeFlexible(meta);

        QString body = item.description;
        if (rationales.contains(item.id)) {
            body = rationales.value(item.id) + QLatin1Char('\n') + body;
        }
        if (selected) {
            const QJsonObject cfg = configFor(item.id);
            body += QLatin1Char('\n')
                    + tr("Config: epochs=%1, batch=%2, lr=%3, seed=%4")
                          .arg(cfg.value(QStringLiteral("epochs")).toInt())
                          .arg(cfg.value(QStringLiteral("batch_size")).toInt())
                          .arg(cfg.value(QStringLiteral("lr")).toDouble())
                          .arg(cfg.value(QStringLiteral("seed")).toInt());
        }

        auto *desc = new QLabel(body, row);
        desc->setObjectName(QStringLiteral("planStepRationale"));
        desc->setWordWrap(true);
        makeFlexible(desc);

        rowLayout->addWidget(header);
        rowLayout->addWidget(meta);
        rowLayout->addWidget(desc);
        templateListLayout_->addWidget(row);
    }
}

void NeuroStudioPage::selectTemplate(const QString &templateId)
{
    if (!TemplateCatalog::find(templateId)) {
        return;
    }
    selectedTemplateId_ = templateId;
    if (!templateConfigs_.contains(templateId)) {
        templateConfigs_.insert(templateId, TemplateCatalog::defaultConfig(templateId));
    }
    rebuildTemplateList();
    rebuildTuneForm();
    updateTrainActionsEnabled();
}

void NeuroStudioPage::configureTemplate(const QString &templateId)
{
    if (!TemplateCatalog::find(templateId)) {
        return;
    }

    TemplateEditDialog dialog(templateId, configFor(templateId), this);
    if (dialog.exec() != QDialog::Accepted) {
        return;
    }

    templateConfigs_.insert(templateId, dialog.config());
    selectedTemplateId_ = templateId;
    rebuildTemplateList();
    rebuildTuneForm();
    updateTrainActionsEnabled();
}

void NeuroStudioPage::rebuildTuneForm()
{
    if (tuneForm_ == nullptr) {
        return;
    }

    // Clear previous editors.
    while (QLayoutItem *item = tuneForm_->takeAt(0)) {
        if (QWidget *widget = item->widget()) {
            widget->deleteLater();
        }
        delete item;
    }
    tuneEditors_.clear();
    tuneError_->clear();
    tuneError_->setVisible(false);

    const TemplateCatalog::TemplateDefinition *def = TemplateCatalog::find(selectedTemplateId_);
    if (def == nullptr) {
        tuneStatus_->setText(tr("Select a template to tune hyperparameters manually."));
        resetTuneButton_->setEnabled(false);
        return;
    }

    tuneStatus_->setText(
        tr("Tuning “%1”. Changes apply immediately to the selected recipe (no auto-search).")
            .arg(def->title));
    resetTuneButton_->setEnabled(true);

    const QJsonObject config = configFor(selectedTemplateId_);
    tuneUpdating_ = true;

    auto addSection = [this](const QString &title) {
        auto *label = new QLabel(title, tuneFormHost_);
        label->setObjectName(QStringLiteral("groupLabel"));
        tuneForm_->addRow(label);
    };

    auto addParams = [this, &config](const QVector<TemplateCatalog::ParamSchema> &schemas) {
        for (const TemplateCatalog::ParamSchema &schema : schemas) {
            const QJsonValue current = config.contains(schema.id) ? config.value(schema.id)
                                                                  : schema.defaultValue;
            QWidget *editor = nullptr;

            switch (schema.type) {
            case TemplateCatalog::ParamType::Boolean: {
                auto *box = new QCheckBox(tuneFormHost_);
                box->setChecked(current.toBool(schema.defaultValue.toBool()));
                connect(box, &QCheckBox::toggled, this, [this](bool) {
                    if (!tuneUpdating_) {
                        applyTuneFormToConfig();
                    }
                });
                editor = box;
                break;
            }
            case TemplateCatalog::ParamType::Enum: {
                auto *combo = new QComboBox(tuneFormHost_);
                combo->addItems(schema.enumValues);
                const QString value = current.toString(schema.defaultValue.toString());
                const int index = combo->findText(value);
                combo->setCurrentIndex(index >= 0 ? index : 0);
                connect(combo, &QComboBox::currentTextChanged, this, [this](const QString &) {
                    if (!tuneUpdating_) {
                        applyTuneFormToConfig();
                    }
                });
                editor = combo;
                break;
            }
            case TemplateCatalog::ParamType::String: {
                auto *line = new QLineEdit(tuneFormHost_);
                line->setText(current.toString(schema.defaultValue.toString()));
                connect(line, &QLineEdit::editingFinished, this, [this]() {
                    if (!tuneUpdating_) {
                        applyTuneFormToConfig();
                    }
                });
                editor = line;
                break;
            }
            case TemplateCatalog::ParamType::Integer:
            case TemplateCatalog::ParamType::Number: {
                auto *spin = new QDoubleSpinBox(tuneFormHost_);
                spin->setDecimals(schema.type == TemplateCatalog::ParamType::Integer ? 0 : 6);
                spin->setMinimum(schema.minimum.value_or(-1.0e9));
                spin->setMaximum(schema.maximum.value_or(1.0e9));
                spin->setSingleStep(schema.type == TemplateCatalog::ParamType::Integer ? 1.0
                                                                                       : 0.0001);
                if (!schema.unit.isEmpty()) {
                    spin->setSuffix(QStringLiteral(" %1").arg(schema.unit));
                }
                spin->setValue(current.toDouble(schema.defaultValue.toDouble()));
                connect(spin, qOverload<double>(&QDoubleSpinBox::valueChanged), this, [this](double) {
                    if (!tuneUpdating_) {
                        applyTuneFormToConfig();
                    }
                });
                editor = spin;
                break;
            }
            }

            if (editor == nullptr) {
                continue;
            }
            tuneEditors_.insert(schema.id, editor);
            auto *label = new QLabel(schema.label, tuneFormHost_);
            if (!schema.help.isEmpty()) {
                label->setToolTip(schema.help);
                editor->setToolTip(schema.help);
            }
            tuneForm_->addRow(label, editor);
        }
    };

    addSection(tr("Model"));
    addParams(def->hyperparams);
    addSection(tr("Train"));
    addParams(def->train);

    tuneUpdating_ = false;
}

void NeuroStudioPage::syncTuneFormFromConfig()
{
    rebuildTuneForm();
}

void NeuroStudioPage::applyTuneFormToConfig()
{
    if (selectedTemplateId_.isEmpty() || TemplateCatalog::find(selectedTemplateId_) == nullptr) {
        return;
    }

    QJsonObject config;
    const TemplateCatalog::TemplateDefinition *def = TemplateCatalog::find(selectedTemplateId_);
    auto collect = [this, &config](const QVector<TemplateCatalog::ParamSchema> &schemas) {
        for (const TemplateCatalog::ParamSchema &schema : schemas) {
            QWidget *editor = tuneEditors_.value(schema.id, nullptr);
            if (editor == nullptr) {
                continue;
            }
            switch (schema.type) {
            case TemplateCatalog::ParamType::Boolean:
                config.insert(schema.id, qobject_cast<QCheckBox *>(editor)->isChecked());
                break;
            case TemplateCatalog::ParamType::Enum:
                config.insert(schema.id, qobject_cast<QComboBox *>(editor)->currentText());
                break;
            case TemplateCatalog::ParamType::String:
                config.insert(schema.id, qobject_cast<QLineEdit *>(editor)->text());
                break;
            case TemplateCatalog::ParamType::Integer: {
                const double value = qobject_cast<QDoubleSpinBox *>(editor)->value();
                config.insert(schema.id, static_cast<int>(qRound(value)));
                break;
            }
            case TemplateCatalog::ParamType::Number:
                config.insert(schema.id, qobject_cast<QDoubleSpinBox *>(editor)->value());
                break;
            }
        }
    };
    collect(def->hyperparams);
    collect(def->train);

    const QString error = TemplateCatalog::validateConfig(selectedTemplateId_, config);
    if (!error.isEmpty()) {
        tuneError_->setText(error);
        tuneError_->setVisible(true);
        return;
    }

    tuneError_->clear();
    tuneError_->setVisible(false);
    templateConfigs_.insert(selectedTemplateId_, config);
    rebuildTemplateList();
}

void NeuroStudioPage::resetTuneDefaults()
{
    if (selectedTemplateId_.isEmpty()) {
        return;
    }
    templateConfigs_.insert(selectedTemplateId_,
                            TemplateCatalog::defaultConfig(selectedTemplateId_));
    rebuildTuneForm();
    rebuildTemplateList();
}

void NeuroStudioPage::startTraining()
{
    if (ProjectDir::instance().root().isEmpty()) {
        QMessageBox::warning(this, tr("No project folder"),
                             tr("Configure a project folder before training."));
        return;
    }
    if (datasetPath_.isEmpty()) {
        QMessageBox::warning(this, tr("No training data"),
                             tr("Choose training data before starting a run."));
        return;
    }
    if (!ProjectDir::instance().contains(datasetPath_)) {
        QMessageBox::warning(this, tr("Invalid data"),
                             tr("Training data must stay inside the project folder."));
        return;
    }
    if (selectedTemplateId_.isEmpty() || !TemplateCatalog::find(selectedTemplateId_)) {
        QMessageBox::warning(this, tr("No template"),
                             tr("Select a template before training."));
        return;
    }
    if (WorkerClient::workersRoot().isEmpty()) {
        QMessageBox::warning(this, tr("Worker missing"),
                             tr("NeuroStudio worker not found."));
        return;
    }
    if (workerClient_->isBusy()) {
        QMessageBox::warning(this, tr("Busy"), tr("A worker is already running."));
        return;
    }

    applyTuneFormToConfig();

    QString preferred = QFileInfo(fullFileName_).completeBaseName();
    if (preferred.isEmpty()) {
        preferred = selectedTemplateId_;
    } else {
        preferred = preferred + QLatin1Char('_') + selectedTemplateId_;
    }

    const StudioTrainIo::Paths paths = StudioTrainIo::suggestPaths(preferred);
    if (paths.runDir.isEmpty()) {
        QMessageBox::warning(this, tr("Train failed"),
                             tr("Could not create a runs/ folder."));
        return;
    }
    trainRunDir_ = paths.runDir;

    const QString device = deviceCombo_->currentData().toString();
    setTrainLoading();
    trainBusy_ = true;
    activeOp_ = QStringLiteral("train");
    updateTrainActionsEnabled();
    updateExportActionsEnabled();

    workerClient_->startRequest(
        QStringLiteral("neurostudio"),
        QStringLiteral("train"),
        QJsonObject{
            {QStringLiteral("input_path"), datasetPath_},
            {QStringLiteral("output_dir"), trainRunDir_},
            {QStringLiteral("template_id"), selectedTemplateId_},
            {QStringLiteral("config"), configFor(selectedTemplateId_)},
            {QStringLiteral("device"), device},
        },
        60 * 60 * 1000);
}

void NeuroStudioPage::cancelTraining()
{
    if (activeOp_ == QLatin1String("train") && workerClient_ != nullptr && workerClient_->isBusy()) {
        workerClient_->cancel();
    }
}

void NeuroStudioPage::startExport()
{
    if (ProjectDir::instance().root().isEmpty()) {
        QMessageBox::warning(this, tr("No project folder"),
                             tr("Configure a project folder before exporting."));
        return;
    }
    const QString checkpoint = lastTrainResult_.value(QStringLiteral("checkpoint_path")).toString();
    if (checkpoint.isEmpty() || !QFileInfo::exists(checkpoint)) {
        QMessageBox::warning(this, tr("No checkpoint"),
                             tr("Train a model first — export needs a checkpoint.pt."));
        return;
    }
    if (!ProjectDir::instance().contains(checkpoint)) {
        QMessageBox::warning(this, tr("Invalid checkpoint"),
                             tr("Checkpoint must stay inside the project folder."));
        return;
    }
    if (WorkerClient::workersRoot().isEmpty()) {
        QMessageBox::warning(this, tr("Worker missing"),
                             tr("NeuroStudio worker not found."));
        return;
    }
    if (workerClient_->isBusy()) {
        QMessageBox::warning(this, tr("Busy"), tr("A worker is already running."));
        return;
    }

    QString preferred = selectedTemplateId_;
    if (preferred.isEmpty()) {
        preferred = QStringLiteral("model");
    }
    preferred = preferred + QLatin1Char('_')
                + exportFormatCombo_->currentData().toString();

    const StudioExportIo::Paths paths = StudioExportIo::suggestPaths(preferred);
    if (paths.modelDir.isEmpty()) {
        QMessageBox::warning(this, tr("Export failed"),
                             tr("Could not create a models/ folder."));
        return;
    }
    exportModelDir_ = paths.modelDir;

    setExportLoading();
    exportBusy_ = true;
    activeOp_ = QStringLiteral("export");
    updateTrainActionsEnabled();
    updateExportActionsEnabled();

    workerClient_->startRequest(
        QStringLiteral("neurostudio"),
        QStringLiteral("export"),
        QJsonObject{
            {QStringLiteral("checkpoint_path"), checkpoint},
            {QStringLiteral("output_dir"), exportModelDir_},
            {QStringLiteral("format"), exportFormatCombo_->currentData().toString()},
            {QStringLiteral("train_meta_path"),
             lastTrainResult_.value(QStringLiteral("train_meta_path")).toString()},
        },
        10 * 60 * 1000);
}

void NeuroStudioPage::cancelExport()
{
    if (activeOp_ == QLatin1String("export") && workerClient_ != nullptr && workerClient_->isBusy()) {
        workerClient_->cancel();
    }
}

void NeuroStudioPage::onWorkerFinished(bool ok,
                                       const QJsonObject &result,
                                       const QString &errorCode,
                                       const QString &errorMessage)
{
    const QString op = activeOp_;
    activeOp_.clear();
    trainBusy_ = false;
    exportBusy_ = false;
    updateTrainActionsEnabled();
    updateExportActionsEnabled();

    if (op == QLatin1String("export")) {
        if (errorCode == QLatin1String("cancelled")) {
            setExportError(tr("Export cancelled."));
            return;
        }
        if (!ok) {
            const QString detail = errorMessage.isEmpty() ? errorCode : errorMessage;
            setExportError(tr("Export failed: %1").arg(detail));
            return;
        }
        const QString outDir = result.value(QStringLiteral("output_dir")).toString(exportModelDir_);
        if (!outDir.isEmpty() && !ProjectDir::instance().contains(outDir)) {
            setExportError(tr("Worker wrote outside the project folder."));
            return;
        }
        setExportReady(result);
        return;
    }

    // Default / train
    if (errorCode == QLatin1String("cancelled")) {
        setTrainError(tr("Training cancelled."));
        return;
    }
    if (!ok) {
        const QString detail = errorMessage.isEmpty() ? errorCode : errorMessage;
        setTrainError(tr("Training failed: %1").arg(detail));
        return;
    }

    const QString outDir = result.value(QStringLiteral("output_dir")).toString(trainRunDir_);
    if (!outDir.isEmpty() && !ProjectDir::instance().contains(outDir)) {
        setTrainError(tr("Worker wrote outside the project folder."));
        return;
    }
    setTrainReady(result);
}

void NeuroStudioPage::onWorkerEvent(const QString &requestId,
                                    const QString &name,
                                    const QJsonObject &data)
{
    Q_UNUSED(requestId);
    if (activeOp_ == QLatin1String("export") && name == QLatin1String("export")) {
        const QString message = data.value(QStringLiteral("message")).toString();
        if (!message.isEmpty()) {
            exportStatus_->setText(message);
        }
        return;
    }

    if (activeOp_ != QLatin1String("train") || name != QLatin1String("metrics")) {
        return;
    }

    const QString message = data.value(QStringLiteral("message")).toString();
    if (!message.isEmpty()) {
        trainStatus_->setText(message);
    }

    if (data.contains(QStringLiteral("epoch"))) {
        liveMetrics_->setVisible(true);
        liveMetrics_->setText(
            tr("Epoch %1/%2   loss %3   acc %4   val_loss %5   val_acc %6")
                .arg(data.value(QStringLiteral("epoch")).toInt())
                .arg(data.value(QStringLiteral("total_epochs")).toInt())
                .arg(data.value(QStringLiteral("loss")).toDouble(), 0, 'f', 4)
                .arg(data.value(QStringLiteral("accuracy")).toDouble(), 0, 'f', 3)
                .arg(data.value(QStringLiteral("val_loss")).toDouble(), 0, 'f', 4)
                .arg(data.value(QStringLiteral("val_accuracy")).toDouble(), 0, 'f', 3));
    }
}

void NeuroStudioPage::onWorkerLog(const QString &redactedLine)
{
    if (activeOp_ == QLatin1String("export") && exportStatus_ != nullptr) {
        if (redactedLine.startsWith(QLatin1String("Loading "))
            || redactedLine.startsWith(QLatin1String("Rebuilding "))
            || redactedLine.startsWith(QLatin1String("Writing "))
            || redactedLine.startsWith(QLatin1String("Exported "))) {
            exportStatus_->setText(redactedLine);
        }
        return;
    }

    if (activeOp_ != QLatin1String("train") || trainLog_ == nullptr) {
        return;
    }
    if (redactedLine.startsWith(QLatin1String("Starting worker:"))) {
        trainLog_->setVisible(true);
        trainLog_->setText(redactedLine);
        return;
    }
    if (redactedLine.startsWith(QLatin1String("Epoch "))
        || redactedLine.startsWith(QLatin1String("Training "))
        || redactedLine.startsWith(QLatin1String("Preparing "))
        || redactedLine.startsWith(QLatin1String("Computing "))
        || redactedLine.startsWith(QLatin1String("Done."))) {
        trainStatus_->setText(redactedLine);
        trainLog_->setVisible(true);
        const QString existing = trainLog_->text();
        if (existing.isEmpty()) {
            trainLog_->setText(redactedLine);
        } else {
            // Keep the log from exploding — retain last ~12 lines.
            QStringList lines = existing.split(QLatin1Char('\n'));
            lines.append(redactedLine);
            while (lines.size() > 12) {
                lines.removeFirst();
            }
            trainLog_->setText(lines.join(QLatin1Char('\n')));
        }
    }
}

void NeuroStudioPage::setTrainIdle()
{
    trainBusy_ = false;
    lastTrainResult_ = {};
    trainStatus_->setText(
        tr("Train the selected template on local data. Metrics stream live; artifacts land in "
           "runs/. Uses real trial labels from epoched events or raw annotations/stim when "
           "present; otherwise falls back to synthetic_demo."));
    trainSkeleton_->setVisible(false);
    liveMetrics_->clear();
    liveMetrics_->setVisible(false);
    finalMetrics_->clear();
    finalMetrics_->setVisible(false);
    artifactsLabel_->clear();
    artifactsLabel_->setVisible(false);
    trainLog_->clear();
    trainLog_->setVisible(false);
    clearConfusion();
    cancelTrainButton_->setVisible(false);
    updateTrainActionsEnabled();
    updateExportActionsEnabled();
}

void NeuroStudioPage::setTrainLoading()
{
    trainStatus_->setText(tr("Starting training…"));
    trainSkeleton_->setVisible(true);
    liveMetrics_->clear();
    liveMetrics_->setVisible(false);
    finalMetrics_->clear();
    finalMetrics_->setVisible(false);
    artifactsLabel_->clear();
    artifactsLabel_->setVisible(false);
    trainLog_->clear();
    trainLog_->setVisible(false);
    clearConfusion();
    cancelTrainButton_->setVisible(true);
    trainButton_->setEnabled(false);
    updateExportActionsEnabled();
}

void NeuroStudioPage::setTrainReady(const QJsonObject &result)
{
    trainSkeleton_->setVisible(false);
    cancelTrainButton_->setVisible(false);

    const QJsonObject metrics = result.value(QStringLiteral("metrics")).toObject();
    const QString dataMode = result.value(QStringLiteral("data_mode")).toString();
    const QString device = result.value(QStringLiteral("device")).toString();

    trainStatus_->setText(tr("Training complete (%1 on %2).").arg(dataMode, device));

    liveMetrics_->setVisible(true);
    liveMetrics_->setText(
        tr("Final   acc %1   bal_acc %2")
            .arg(metrics.value(QStringLiteral("accuracy")).toDouble(), 0, 'f', 3)
            .arg(metrics.value(QStringLiteral("balanced_accuracy")).toDouble(), 0, 'f', 3));

    QStringList finalLines;
    finalLines << tr("Template: %1").arg(result.value(QStringLiteral("template_id")).toString());
    finalLines << tr("Primary metric: %1")
                      .arg(metrics.value(QStringLiteral("primary")).toString(QStringLiteral("accuracy")));
    finalLines << tr("Accuracy: %1")
                      .arg(metrics.value(QStringLiteral("accuracy")).toDouble(), 0, 'f', 4);
    finalLines << tr("Balanced accuracy: %1")
                      .arg(metrics.value(QStringLiteral("balanced_accuracy")).toDouble(), 0, 'f', 4);
    finalLines << tr("Classes: %1").arg(metrics.value(QStringLiteral("n_classes")).toInt());
    const QJsonArray classNames = metrics.value(QStringLiteral("class_names")).toArray();
    if (!classNames.isEmpty()) {
        QStringList names;
        for (const QJsonValue &value : classNames) {
            names << value.toString();
        }
        finalLines << tr("Class names: %1").arg(names.join(QStringLiteral(", ")));
    }
    const QJsonObject dataMeta = result.value(QStringLiteral("data")).toObject();
    const QString labelSource = dataMeta.value(QStringLiteral("label_source")).toString();
    if (!labelSource.isEmpty()) {
        finalLines << tr("Label source: %1").arg(labelSource);
    }
    if (dataMode == QLatin1String("synthetic_demo")) {
        finalLines << tr("Note: synthetic_demo — no usable labels in the FIF; not a science result.");
    } else if (dataMode.startsWith(QLatin1String("labeled_"))) {
        finalLines << tr("Note: trained on real event/annotation labels from the file.");
    }
    finalMetrics_->setText(finalLines.join(QLatin1Char('\n')));
    finalMetrics_->setVisible(true);

    renderConfusion(metrics.value(QStringLiteral("confusion")).toArray());

    QStringList arts;
    const QString ckpt = result.value(QStringLiteral("checkpoint_path")).toString();
    const QString metricsPath = result.value(QStringLiteral("metrics_path")).toString();
    const QString metaPath = result.value(QStringLiteral("train_meta_path")).toString();
    const QString outDir = result.value(QStringLiteral("output_dir")).toString(trainRunDir_);
    if (!outDir.isEmpty()) {
        arts << tr("Run folder: %1").arg(QDir::toNativeSeparators(outDir));
    }
    if (!ckpt.isEmpty()) {
        arts << tr("Checkpoint: %1").arg(QDir::toNativeSeparators(ckpt));
    }
    if (!metricsPath.isEmpty()) {
        arts << tr("Metrics: %1").arg(QDir::toNativeSeparators(metricsPath));
    }
    if (!metaPath.isEmpty()) {
        arts << tr("Train meta: %1").arg(QDir::toNativeSeparators(metaPath));
    }
    artifactsLabel_->setText(arts.join(QLatin1Char('\n')));
    artifactsLabel_->setVisible(!arts.isEmpty());
    lastTrainResult_ = result;
    updateTrainActionsEnabled();
    updateExportActionsEnabled();
}

void NeuroStudioPage::setTrainError(const QString &message)
{
    trainSkeleton_->setVisible(false);
    cancelTrainButton_->setVisible(false);
    trainStatus_->setText(message);
    updateTrainActionsEnabled();
    updateExportActionsEnabled();
}

void NeuroStudioPage::setExportIdle()
{
    exportBusy_ = false;
    exportStatus_->setText(
        tr("Export a trained checkpoint to models/ for local use and Hub. Cloud publish is a "
           "placeholder."));
    exportSkeleton_->setVisible(false);
    exportResult_->clear();
    exportResult_->setVisible(false);
    cancelExportButton_->setVisible(false);
    updateExportActionsEnabled();
}

void NeuroStudioPage::setExportLoading()
{
    exportStatus_->setText(tr("Exporting…"));
    exportSkeleton_->setVisible(true);
    exportResult_->clear();
    exportResult_->setVisible(false);
    cancelExportButton_->setVisible(true);
    exportButton_->setEnabled(false);
}

void NeuroStudioPage::setExportReady(const QJsonObject &result)
{
    exportSkeleton_->setVisible(false);
    cancelExportButton_->setVisible(false);

    const QString fmt = result.value(QStringLiteral("format_label")).toString(
        result.value(QStringLiteral("format")).toString());
    const QString outDir = result.value(QStringLiteral("output_dir")).toString(exportModelDir_);
    const QString artifact = result.value(QStringLiteral("artifact_path")).toString();
    const QString meta = result.value(QStringLiteral("metadata_path")).toString();

    exportStatus_->setText(tr("Export complete (%1).").arg(fmt));

    QStringList lines;
    if (!outDir.isEmpty()) {
        lines << tr("Model folder: %1").arg(QDir::toNativeSeparators(outDir));
    }
    if (!artifact.isEmpty()) {
        lines << tr("Artifact: %1").arg(QDir::toNativeSeparators(artifact));
    }
    if (!meta.isEmpty()) {
        lines << tr("Metadata: %1").arg(QDir::toNativeSeparators(meta));
    }
    lines << tr("Visible in Hub → Local models.");
    exportResult_->setText(lines.join(QLatin1Char('\n')));
    exportResult_->setVisible(true);
    updateExportActionsEnabled();
}

void NeuroStudioPage::setExportError(const QString &message)
{
    exportSkeleton_->setVisible(false);
    cancelExportButton_->setVisible(false);
    exportStatus_->setText(message);
    updateExportActionsEnabled();
}

void NeuroStudioPage::updateTrainActionsEnabled()
{
    if (trainButton_ == nullptr) {
        return;
    }
    const bool workerBusy = workerClient_ != nullptr && workerClient_->isBusy();
    const bool canTrain = !datasetPath_.isEmpty() && !selectedTemplateId_.isEmpty()
                          && !trainBusy_ && !exportBusy_ && !workerBusy;
    trainButton_->setEnabled(canTrain);
    if (deviceCombo_ != nullptr) {
        deviceCombo_->setEnabled(!trainBusy_ && !exportBusy_);
    }
}

void NeuroStudioPage::updateExportActionsEnabled()
{
    if (exportButton_ == nullptr) {
        return;
    }
    const bool workerBusy = workerClient_ != nullptr && workerClient_->isBusy();
    const QString checkpoint = lastTrainResult_.value(QStringLiteral("checkpoint_path")).toString();
    const bool canExport = !checkpoint.isEmpty() && QFileInfo::exists(checkpoint) && !trainBusy_
                           && !exportBusy_ && !workerBusy;
    exportButton_->setEnabled(canExport);
    if (exportFormatCombo_ != nullptr) {
        exportFormatCombo_->setEnabled(!exportBusy_ && !trainBusy_);
    }
    // Placeholder stays disabled — cloud not wired.
    if (publishPlaceholderButton_ != nullptr) {
        publishPlaceholderButton_->setEnabled(false);
    }
}

void NeuroStudioPage::renderConfusion(const QJsonArray &matrix)
{
    clearConfusion();
    if (matrix.isEmpty()) {
        return;
    }

    auto *title = new QLabel(tr("Confusion matrix (rows=true, cols=pred)"), confusionHost_);
    title->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(title);
    confusionLayout_->addWidget(title);

    auto *gridHost = new QWidget(confusionHost_);
    makeFlexible(gridHost);
    auto *grid = new QGridLayout(gridHost);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(6);
    grid->setVerticalSpacing(4);

    for (int r = 0; r < matrix.size(); ++r) {
        const QJsonArray row = matrix.at(r).toArray();
        for (int c = 0; c < row.size(); ++c) {
            auto *cell = new QLabel(QString::number(row.at(c).toInt()), gridHost);
            cell->setObjectName(QStringLiteral("planStepMeta"));
            cell->setAlignment(Qt::AlignCenter);
            cell->setMinimumWidth(28);
            grid->addWidget(cell, r, c);
        }
    }
    confusionLayout_->addWidget(gridHost);
    confusionHost_->setVisible(true);
}

void NeuroStudioPage::clearConfusion()
{
    if (confusionLayout_ == nullptr) {
        return;
    }
    while (QLayoutItem *item = confusionLayout_->takeAt(0)) {
        if (QWidget *widget = item->widget()) {
            widget->deleteLater();
        }
        delete item;
    }
    confusionHost_->setVisible(false);
}

QJsonObject NeuroStudioPage::configFor(const QString &templateId) const
{
    if (templateId.isEmpty()) {
        return {};
    }
    if (templateConfigs_.contains(templateId)) {
        return templateConfigs_.value(templateId);
    }
    return TemplateCatalog::defaultConfig(templateId);
}

void NeuroStudioPage::refreshIcons()
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

void NeuroStudioPage::updateElidedTexts()
{
    if (fileNameLabel_ == nullptr || filePathLabel_ == nullptr) {
        return;
    }

    const int nameWidth = qMax(80, fileNameLabel_->width());
    const int pathWidth = qMax(80, filePathLabel_->width());
    const QFontMetrics nameMetrics(fileNameLabel_->font());
    const QFontMetrics pathMetrics(filePathLabel_->font());

    fileNameLabel_->setText(nameMetrics.elidedText(fullFileName_, Qt::ElideMiddle, nameWidth));
    fileNameLabel_->setToolTip(fullFileName_);
    filePathLabel_->setText(pathMetrics.elidedText(fullFilePath_, Qt::ElideMiddle, pathWidth));
    filePathLabel_->setToolTip(fullFilePath_);
}

QString NeuroStudioPage::formatFileSize(qint64 bytes)
{
    constexpr qreal kb = 1024.0;
    constexpr qreal mb = kb * 1024.0;
    constexpr qreal gb = mb * 1024.0;
    if (bytes >= static_cast<qint64>(gb)) {
        return QStringLiteral("%1 GB").arg(bytes / gb, 0, 'f', 2);
    }
    if (bytes >= static_cast<qint64>(mb)) {
        return QStringLiteral("%1 MB").arg(bytes / mb, 0, 'f', 1);
    }
    if (bytes >= static_cast<qint64>(kb)) {
        return QStringLiteral("%1 KB").arg(bytes / kb, 0, 'f', 0);
    }
    return QStringLiteral("%1 B").arg(bytes);
}

QString NeuroStudioPage::kindLabel(const QString &kind)
{
    if (kind == QLatin1String("run_output")) {
        return QObject::tr("NeuroFlow run output");
    }
    if (kind == QLatin1String("dataset")) {
        return QObject::tr("Project dataset");
    }
    return QObject::tr("In project folder");
}

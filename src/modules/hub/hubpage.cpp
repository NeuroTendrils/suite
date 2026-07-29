#include "modules/hub/hubpage.hpp"

#include "core/modellibrary.hpp"
#include "core/projectdir.hpp"
#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QDir>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QLabel>
#include <QMessageBox>
#include <QPushButton>
#include <QScrollArea>
#include <QShowEvent>
#include <QSizePolicy>
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

HubPage::HubPage(QWidget *parent)
    : QWidget(parent)
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

    auto *content = new QWidget;
    content->setObjectName(QStringLiteral("pageContent"));
    makeFlexible(content);
    content->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    auto *layout = new QVBoxLayout(content);
    layout->setContentsMargins(20, 16, 20, 20);
    layout->setSpacing(0);

    auto *header = new PageHeader(
        tr("NeuroTendrils Hub"),
        tr("Browse local models exported from NeuroStudio. Plans and datasets expand in a later "
           "phase."),
        content);

    auto *modelsLabel = new QLabel(tr("Local models"), content);
    modelsLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(modelsLabel);

    auto *modelsPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *modelsLayout = new QVBoxLayout(modelsPanel);
    modelsLayout->setContentsMargins(12, 12, 12, 12);
    modelsLayout->setSpacing(8);

    libraryStatus_ = new QLabel(modelsPanel);
    libraryStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    libraryStatus_->setWordWrap(true);
    makeFlexible(libraryStatus_);

    librarySkeleton_ = new SkeletonLoader(modelsPanel);
    librarySkeleton_->addBlock(1.0, 52, 8);
    librarySkeleton_->addBlock(1.0, 52, 8);
    librarySkeleton_->setVisible(false);

    modelListHost_ = new QWidget(modelsPanel);
    makeFlexible(modelListHost_);
    modelListLayout_ = new QVBoxLayout(modelListHost_);
    modelListLayout_->setContentsMargins(0, 0, 0, 0);
    modelListLayout_->setSpacing(8);

    refreshButton_ = new QPushButton(tr("Refresh"), modelsPanel);
    refreshButton_->setObjectName(QStringLiteral("secondaryButton"));
    refreshButton_->setCursor(Qt::PointingHandCursor);
    refreshButton_->setAutoDefault(false);
    connect(refreshButton_, &QPushButton::clicked, this, &HubPage::refreshLibrary);

    auto *refreshRow = new QWidget(modelsPanel);
    makeFlexible(refreshRow);
    auto *refreshRowLayout = new QHBoxLayout(refreshRow);
    refreshRowLayout->setContentsMargins(0, 0, 0, 0);
    refreshRowLayout->addWidget(refreshButton_, 0, Qt::AlignLeft);
    refreshRowLayout->addStretch(1);

    modelsLayout->addWidget(libraryStatus_);
    modelsLayout->addWidget(librarySkeleton_);
    modelsLayout->addWidget(modelListHost_);
    modelsLayout->addWidget(refreshRow);

    auto *cloudLabel = new QLabel(tr("Cloud"), content);
    cloudLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(cloudLabel);

    auto *cloudPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *cloudLayout = new QVBoxLayout(cloudPanel);
    cloudLayout->setContentsMargins(12, 12, 12, 12);
    cloudLayout->setSpacing(8);

    cloudStatus_ = new QLabel(
        tr("Sign-in and cloud usage are placeholders. Models stay on this computer under models/."),
        cloudPanel);
    cloudStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    cloudStatus_->setWordWrap(true);
    makeFlexible(cloudStatus_);

    signInPlaceholder_ = new QPushButton(tr("Sign in…"), cloudPanel);
    signInPlaceholder_->setObjectName(QStringLiteral("secondaryButton"));
    signInPlaceholder_->setCursor(Qt::PointingHandCursor);
    signInPlaceholder_->setAutoDefault(false);
    signInPlaceholder_->setEnabled(false);
    signInPlaceholder_->setToolTip(tr("Cloud sign-in is not available yet."));
    connect(signInPlaceholder_, &QPushButton::clicked, this, &HubPage::onPublishPlaceholder);

    auto *publishNote = new QLabel(
        tr("Publish / share (Kaggle- or HF-style) will land with cloud features — not in this "
           "phase."),
        cloudPanel);
    publishNote->setObjectName(QStringLiteral("upcomingCaption"));
    publishNote->setWordWrap(true);
    makeFlexible(publishNote);

    cloudLayout->addWidget(cloudStatus_);
    cloudLayout->addWidget(signInPlaceholder_, 0, Qt::AlignLeft);
    cloudLayout->addWidget(publishNote);

    layout->addWidget(header);
    layout->addSpacing(16);
    layout->addWidget(modelsLabel);
    layout->addSpacing(6);
    layout->addWidget(modelsPanel);
    layout->addSpacing(16);
    layout->addWidget(cloudLabel);
    layout->addSpacing(6);
    layout->addWidget(cloudPanel);
    layout->addStretch(1);

    scroll->setWidget(content);
    rootLayout->addWidget(scroll);

    refreshLibrary();
}

void HubPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    refreshLibrary();
}

void HubPage::refreshLibrary()
{
    librarySkeleton_->setVisible(true);
    modelListHost_->setVisible(false);
    rebuildModelList();
    librarySkeleton_->setVisible(false);
    modelListHost_->setVisible(true);
}

void HubPage::rebuildModelList()
{
    while (QLayoutItem *item = modelListLayout_->takeAt(0)) {
        if (QWidget *widget = item->widget()) {
            widget->deleteLater();
        }
        delete item;
    }

    if (ProjectDir::instance().root().isEmpty()) {
        libraryStatus_->setText(tr("Configure a project folder to index local models."));
        return;
    }

    const QVector<ModelLibrary::Entry> entries = ModelLibrary::scan();
    if (entries.isEmpty()) {
        libraryStatus_->setText(
            tr("No exported models yet. Train in NeuroStudio, then Export — artifacts land in "
               "%1.")
                .arg(QDir::toNativeSeparators(ProjectDir::instance().modelsDir())));
        return;
    }

    libraryStatus_->setText(
        tr("%n local model(s) in models/. Newest first.", nullptr, entries.size()));

    for (const ModelLibrary::Entry &entry : entries) {
        auto *row = new QFrame(modelListHost_);
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

        auto *title = new QLabel(entry.title, header);
        title->setObjectName(QStringLiteral("planStepTitle"));
        makeFlexible(title);

        auto *publishButton = new QPushButton(tr("Publish…"), header);
        publishButton->setObjectName(QStringLiteral("planStepButton"));
        publishButton->setCursor(Qt::PointingHandCursor);
        publishButton->setAutoDefault(false);
        publishButton->setEnabled(false);
        publishButton->setToolTip(tr("Cloud publish is a placeholder."));
        connect(publishButton, &QPushButton::clicked, this, &HubPage::onPublishPlaceholder);

        headerLayout->addWidget(title, 1, Qt::AlignVCenter);
        headerLayout->addWidget(publishButton, 0, Qt::AlignVCenter);

        QStringList metaBits;
        if (!entry.formatLabel.isEmpty()) {
            metaBits << entry.formatLabel;
        }
        if (!entry.templateId.isEmpty()) {
            metaBits << entry.templateId;
        }
        if (!entry.publishStatus.isEmpty()) {
            metaBits << entry.publishStatus;
        }
        auto *meta = new QLabel(metaBits.join(QStringLiteral(" · ")), row);
        meta->setObjectName(QStringLiteral("planStepMeta"));
        meta->setWordWrap(true);
        makeFlexible(meta);

        QStringList body;
        body << tr("Folder: %1").arg(QDir::toNativeSeparators(entry.modelDir));
        if (!entry.artifactPath.isEmpty()) {
            body << tr("Artifact: %1").arg(QDir::toNativeSeparators(entry.artifactPath));
        }
        if (!entry.exportedAt.isEmpty()) {
            body << tr("Exported: %1").arg(entry.exportedAt);
        }
        const QJsonObject metrics = entry.meta.value(QStringLiteral("metrics")).toObject();
        if (!metrics.isEmpty()) {
            body << tr("Accuracy: %1")
                        .arg(metrics.value(QStringLiteral("accuracy")).toDouble(), 0, 'f', 3);
        }

        auto *desc = new QLabel(body.join(QLatin1Char('\n')), row);
        desc->setObjectName(QStringLiteral("planStepRationale"));
        desc->setWordWrap(true);
        desc->setTextInteractionFlags(Qt::TextSelectableByMouse);
        makeFlexible(desc);

        rowLayout->addWidget(header);
        rowLayout->addWidget(meta);
        rowLayout->addWidget(desc);
        modelListLayout_->addWidget(row);
    }
}

void HubPage::onPublishPlaceholder()
{
    QMessageBox::information(
        this,
        tr("Cloud publish"),
        tr("Cloud publish and sharing are placeholders. Your models remain local under models/."));
}

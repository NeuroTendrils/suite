#include "modules/hub/hubpage.hpp"

#include "core/projectdir.hpp"
#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QComboBox>
#include <QDir>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
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

QString entryKey(const LocalLibrary::Entry &entry)
{
    return LocalLibrary::kindLabel(entry.kind) + QLatin1Char(':') + entry.id + QLatin1Char('@')
           + entry.path;
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
        tr("Local library of plans, datasets, and models — plus cloud and sharing placeholders."),
        content);

    // --- Local library ---
    auto *libraryLabel = new QLabel(tr("Local library"), content);
    libraryLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(libraryLabel);

    auto *libraryPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *libraryLayout = new QVBoxLayout(libraryPanel);
    libraryLayout->setContentsMargins(12, 12, 12, 12);
    libraryLayout->setSpacing(8);

    auto *toolbar = new QWidget(libraryPanel);
    makeFlexible(toolbar);
    auto *toolbarLayout = new QHBoxLayout(toolbar);
    toolbarLayout->setContentsMargins(0, 0, 0, 0);
    toolbarLayout->setSpacing(8);

    auto *filterLabel = new QLabel(tr("Show"), toolbar);
    filterLabel->setObjectName(QStringLiteral("upcomingCaption"));
    filterCombo_ = new QComboBox(toolbar);
    filterCombo_->addItem(tr("All"), static_cast<int>(Filter::All));
    filterCombo_->addItem(tr("Plans"), static_cast<int>(Filter::Plans));
    filterCombo_->addItem(tr("Datasets"), static_cast<int>(Filter::Datasets));
    filterCombo_->addItem(tr("Models"), static_cast<int>(Filter::Models));
    connect(filterCombo_, QOverload<int>::of(&QComboBox::currentIndexChanged), this,
            &HubPage::onFilterChanged);

    refreshButton_ = new QPushButton(tr("Refresh"), toolbar);
    refreshButton_->setObjectName(QStringLiteral("secondaryButton"));
    refreshButton_->setCursor(Qt::PointingHandCursor);
    refreshButton_->setAutoDefault(false);
    connect(refreshButton_, &QPushButton::clicked, this, &HubPage::refreshLibrary);

    toolbarLayout->addWidget(filterLabel, 0);
    toolbarLayout->addWidget(filterCombo_, 0);
    toolbarLayout->addStretch(1);
    toolbarLayout->addWidget(refreshButton_, 0);

    libraryStatus_ = new QLabel(libraryPanel);
    libraryStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    libraryStatus_->setWordWrap(true);
    makeFlexible(libraryStatus_);

    librarySkeleton_ = new SkeletonLoader(libraryPanel);
    librarySkeleton_->addBlock(1.0, 52, 8);
    librarySkeleton_->addBlock(1.0, 52, 8);
    librarySkeleton_->addBlock(0.7, 52, 8);
    librarySkeleton_->setVisible(false);

    listHost_ = new QWidget(libraryPanel);
    makeFlexible(listHost_);
    listLayout_ = new QVBoxLayout(listHost_);
    listLayout_->setContentsMargins(0, 0, 0, 0);
    listLayout_->setSpacing(8);

    libraryLayout->addWidget(toolbar);
    libraryLayout->addWidget(libraryStatus_);
    libraryLayout->addWidget(librarySkeleton_);
    libraryLayout->addWidget(listHost_);

    // --- Detail ---
    auto *detailLabel = new QLabel(tr("Details"), content);
    detailLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(detailLabel);

    detailPanel_ = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *detailLayout = new QVBoxLayout(detailPanel_);
    detailLayout->setContentsMargins(12, 12, 12, 12);
    detailLayout->setSpacing(8);

    detailTitle_ = new QLabel(detailPanel_);
    detailTitle_->setObjectName(QStringLiteral("planStepTitle"));
    detailTitle_->setWordWrap(true);
    makeFlexible(detailTitle_);

    detailMeta_ = new QLabel(detailPanel_);
    detailMeta_->setObjectName(QStringLiteral("planStepMeta"));
    detailMeta_->setWordWrap(true);
    makeFlexible(detailMeta_);

    detailBody_ = new QLabel(detailPanel_);
    detailBody_->setObjectName(QStringLiteral("planStepRationale"));
    detailBody_->setWordWrap(true);
    detailBody_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    makeFlexible(detailBody_);

    detailShareButton_ = new QPushButton(tr("Share…"), detailPanel_);
    detailShareButton_->setObjectName(QStringLiteral("secondaryButton"));
    detailShareButton_->setCursor(Qt::PointingHandCursor);
    detailShareButton_->setAutoDefault(false);
    detailShareButton_->setEnabled(false);
    connect(detailShareButton_, &QPushButton::clicked, this, &HubPage::onSharePlaceholder);

    detailPublishButton_ = new QPushButton(tr("Publish…"), detailPanel_);
    detailPublishButton_->setObjectName(QStringLiteral("secondaryButton"));
    detailPublishButton_->setCursor(Qt::PointingHandCursor);
    detailPublishButton_->setAutoDefault(false);
    detailPublishButton_->setEnabled(false);
    connect(detailPublishButton_, &QPushButton::clicked, this, &HubPage::onPublishPlaceholder);

    auto *detailActions = new QWidget(detailPanel_);
    makeFlexible(detailActions);
    auto *detailActionsLayout = new QHBoxLayout(detailActions);
    detailActionsLayout->setContentsMargins(0, 0, 0, 0);
    detailActionsLayout->setSpacing(8);
    detailActionsLayout->addWidget(detailShareButton_, 0, Qt::AlignLeft);
    detailActionsLayout->addWidget(detailPublishButton_, 0, Qt::AlignLeft);
    detailActionsLayout->addStretch(1);

    detailLayout->addWidget(detailTitle_);
    detailLayout->addWidget(detailMeta_);
    detailLayout->addWidget(detailBody_);
    detailLayout->addWidget(detailActions);

    // --- Cloud ---
    auto *cloudLabel = new QLabel(tr("Cloud"), content);
    cloudLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(cloudLabel);

    auto *cloudPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *cloudLayout = new QVBoxLayout(cloudPanel);
    cloudLayout->setContentsMargins(12, 12, 12, 12);
    cloudLayout->setSpacing(8);

    cloudStatus_ = new QLabel(
        tr("Not signed in. Cloud sync and remote storage are placeholders — everything stays on "
           "this computer for now."),
        cloudPanel);
    cloudStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    cloudStatus_->setWordWrap(true);
    makeFlexible(cloudStatus_);

    usagePlaceholder_ = new QLabel(
        tr("Usage (placeholder)\n"
           "Storage: — / — GB\n"
           "Private models: —\n"
           "Org seats: —"),
        cloudPanel);
    usagePlaceholder_->setObjectName(QStringLiteral("planStepRationale"));
    usagePlaceholder_->setWordWrap(true);
    makeFlexible(usagePlaceholder_);

    signInPlaceholder_ = new QPushButton(tr("Sign in…"), cloudPanel);
    signInPlaceholder_->setObjectName(QStringLiteral("secondaryButton"));
    signInPlaceholder_->setCursor(Qt::PointingHandCursor);
    signInPlaceholder_->setAutoDefault(false);
    signInPlaceholder_->setEnabled(false);
    signInPlaceholder_->setToolTip(tr("Cloud sign-in is not available yet."));
    connect(signInPlaceholder_, &QPushButton::clicked, this, &HubPage::onSignInPlaceholder);

    cloudLayout->addWidget(cloudStatus_);
    cloudLayout->addWidget(usagePlaceholder_);
    cloudLayout->addWidget(signInPlaceholder_, 0, Qt::AlignLeft);

    // --- Sharing ---
    auto *sharingLabel = new QLabel(tr("Sharing"), content);
    sharingLabel->setObjectName(QStringLiteral("groupLabel"));
    makeFlexible(sharingLabel);

    auto *sharingPanel = makePanel(QStringLiteral("fingerprintPanel"), content);
    auto *sharingLayout = new QVBoxLayout(sharingPanel);
    sharingLayout->setContentsMargins(12, 12, 12, 12);
    sharingLayout->setSpacing(8);

    sharingStatus_ = new QLabel(
        tr("Share EEG plans, datasets, and models like a Kaggle / Hugging Face hub — orgs and "
           "private visibility come later. Controls below are placeholders."),
        sharingPanel);
    sharingStatus_->setObjectName(QStringLiteral("upcomingCaption"));
    sharingStatus_->setWordWrap(true);
    makeFlexible(sharingStatus_);

    auto *visibilityRow = new QWidget(sharingPanel);
    makeFlexible(visibilityRow);
    auto *visibilityRowLayout = new QHBoxLayout(visibilityRow);
    visibilityRowLayout->setContentsMargins(0, 0, 0, 0);
    visibilityRowLayout->setSpacing(8);
    auto *visibilityLabel = new QLabel(tr("Visibility"), visibilityRow);
    visibilityLabel->setObjectName(QStringLiteral("upcomingCaption"));
    visibilityCombo_ = new QComboBox(visibilityRow);
    visibilityCombo_->addItem(tr("Private"));
    visibilityCombo_->addItem(tr("Organization"));
    visibilityCombo_->addItem(tr("Public"));
    visibilityCombo_->setEnabled(false);
    visibilityCombo_->setToolTip(tr("Visibility controls are placeholders."));
    visibilityRowLayout->addWidget(visibilityLabel, 0);
    visibilityRowLayout->addWidget(visibilityCombo_, 0);
    visibilityRowLayout->addStretch(1);

    shareHfButton_ = new QPushButton(tr("Share to Hugging Face…"), sharingPanel);
    shareHfButton_->setObjectName(QStringLiteral("secondaryButton"));
    shareHfButton_->setCursor(Qt::PointingHandCursor);
    shareHfButton_->setAutoDefault(false);
    shareHfButton_->setEnabled(false);
    connect(shareHfButton_, &QPushButton::clicked, this, &HubPage::onSharePlaceholder);

    shareKaggleButton_ = new QPushButton(tr("Share to Kaggle…"), sharingPanel);
    shareKaggleButton_->setObjectName(QStringLiteral("secondaryButton"));
    shareKaggleButton_->setCursor(Qt::PointingHandCursor);
    shareKaggleButton_->setAutoDefault(false);
    shareKaggleButton_->setEnabled(false);
    connect(shareKaggleButton_, &QPushButton::clicked, this, &HubPage::onSharePlaceholder);

    auto *shareActions = new QWidget(sharingPanel);
    makeFlexible(shareActions);
    auto *shareActionsLayout = new QHBoxLayout(shareActions);
    shareActionsLayout->setContentsMargins(0, 0, 0, 0);
    shareActionsLayout->setSpacing(8);
    shareActionsLayout->addWidget(shareHfButton_, 0, Qt::AlignLeft);
    shareActionsLayout->addWidget(shareKaggleButton_, 0, Qt::AlignLeft);
    shareActionsLayout->addStretch(1);

    sharingLayout->addWidget(sharingStatus_);
    sharingLayout->addWidget(visibilityRow);
    sharingLayout->addWidget(shareActions);

    layout->addWidget(header);
    layout->addSpacing(16);
    layout->addWidget(libraryLabel);
    layout->addSpacing(6);
    layout->addWidget(libraryPanel);
    layout->addSpacing(16);
    layout->addWidget(detailLabel);
    layout->addSpacing(6);
    layout->addWidget(detailPanel_);
    layout->addSpacing(16);
    layout->addWidget(cloudLabel);
    layout->addSpacing(6);
    layout->addWidget(cloudPanel);
    layout->addSpacing(16);
    layout->addWidget(sharingLabel);
    layout->addSpacing(6);
    layout->addWidget(sharingPanel);
    layout->addStretch(1);

    scroll->setWidget(content);
    rootLayout->addWidget(scroll);

    clearDetail();
    refreshLibrary();
}

void HubPage::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    refreshLibrary();
}

void HubPage::onFilterChanged(int index)
{
    Q_UNUSED(index);
    filter_ = static_cast<Filter>(filterCombo_->currentData().toInt());
    rebuildList();
}

void HubPage::refreshLibrary()
{
    librarySkeleton_->setVisible(true);
    listHost_->setVisible(false);
    index_ = LocalLibrary::scan();
    rebuildList();
    librarySkeleton_->setVisible(false);
    listHost_->setVisible(true);
}

QVector<LocalLibrary::Entry> HubPage::filteredEntries() const
{
    QVector<LocalLibrary::Entry> out;
    auto append = [&](const QVector<LocalLibrary::Entry> &bucket) {
        for (const LocalLibrary::Entry &entry : bucket) {
            out.append(entry);
        }
    };

    switch (filter_) {
    case Filter::Plans:
        append(index_.plans);
        break;
    case Filter::Datasets:
        append(index_.datasets);
        break;
    case Filter::Models:
        append(index_.models);
        break;
    case Filter::All:
        append(index_.plans);
        append(index_.datasets);
        append(index_.models);
        break;
    }
    return out;
}

void HubPage::rebuildList()
{
    while (QLayoutItem *item = listLayout_->takeAt(0)) {
        if (QWidget *widget = item->widget()) {
            widget->deleteLater();
        }
        delete item;
    }

    if (ProjectDir::instance().root().isEmpty()) {
        libraryStatus_->setText(tr("Configure a project folder to index the local library."));
        clearDetail();
        return;
    }

    const QVector<LocalLibrary::Entry> entries = filteredEntries();
    libraryStatus_->setText(
        tr("%1 item(s) — %2 plan(s), %3 dataset(s), %4 model(s). Select one for details.")
            .arg(entries.size())
            .arg(index_.plans.size())
            .arg(index_.datasets.size())
            .arg(index_.models.size()));

    if (entries.isEmpty()) {
        auto *empty = new QLabel(
            tr("Nothing here yet. Import data in NeuroFlow, save a plan, or export a model from "
               "NeuroStudio."),
            listHost_);
        empty->setObjectName(QStringLiteral("upcomingCaption"));
        empty->setWordWrap(true);
        makeFlexible(empty);
        listLayout_->addWidget(empty);
        clearDetail();
        return;
    }

    bool selectionAlive = false;
    for (const LocalLibrary::Entry &entry : entries) {
        const QString key = entryKey(entry);
        if (key == selectedKey_) {
            selectionAlive = true;
        }

        auto *row = new QFrame(listHost_);
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

        auto *badge = new QLabel(LocalLibrary::kindLabel(entry.kind), header);
        badge->setObjectName(QStringLiteral("fileBadge"));
        badge->setAlignment(Qt::AlignCenter);

        auto *title = new QLabel(entry.title, header);
        title->setObjectName(QStringLiteral("planStepTitle"));
        makeFlexible(title);

        auto *openButton = new QPushButton(tr("Details"), header);
        openButton->setObjectName(QStringLiteral("planStepButton"));
        openButton->setCursor(Qt::PointingHandCursor);
        openButton->setAutoDefault(false);
        connect(openButton, &QPushButton::clicked, this, [this, entry]() {
            selectedKey_ = entryKey(entry);
            showDetail(entry);
            rebuildList();
        });

        headerLayout->addWidget(badge, 0, Qt::AlignVCenter);
        headerLayout->addWidget(title, 1, Qt::AlignVCenter);
        headerLayout->addWidget(openButton, 0, Qt::AlignVCenter);

        auto *meta = new QLabel(entry.subtitle, row);
        meta->setObjectName(QStringLiteral("planStepMeta"));
        meta->setWordWrap(true);
        makeFlexible(meta);

        if (key == selectedKey_) {
            title->setText(tr("Selected · %1").arg(entry.title));
        }

        rowLayout->addWidget(header);
        rowLayout->addWidget(meta);
        listLayout_->addWidget(row);
    }

    if (!selectionAlive) {
        clearDetail();
    }
}

void HubPage::showDetail(const LocalLibrary::Entry &entry)
{
    detailTitle_->setText(entry.title);
    detailMeta_->setText(
        tr("%1 · %2")
            .arg(LocalLibrary::kindLabel(entry.kind),
                 entry.subtitle.isEmpty() ? tr("Local") : entry.subtitle));

    QStringList body;
    body << tr("Path: %1").arg(QDir::toNativeSeparators(entry.path));
    if (entry.sizeBytes > 0) {
        body << tr("Size: %1").arg(formatSize(entry.sizeBytes));
    }
    if (!entry.modified.isEmpty()) {
        body << tr("Modified: %1").arg(entry.modified);
    }

    if (entry.kind == LocalLibrary::Kind::Plan) {
        const int steps = entry.meta.value(QStringLiteral("steps")).toArray().size();
        body << tr("Steps: %1").arg(steps);
        const QString dataset = entry.meta.value(QStringLiteral("dataset_path")).toString();
        if (!dataset.isEmpty()) {
            body << tr("Linked data: %1").arg(QDir::toNativeSeparators(dataset));
        }
        const QString savedAt = entry.meta.value(QStringLiteral("saved_at")).toString();
        if (!savedAt.isEmpty()) {
            body << tr("Saved: %1").arg(savedAt);
        }
    } else if (entry.kind == LocalLibrary::Kind::Model) {
        const QString artifact = entry.meta.value(QStringLiteral("artifact_path")).toString();
        if (!artifact.isEmpty()) {
            body << tr("Artifact: %1").arg(QDir::toNativeSeparators(artifact));
        }
        const QString templateId = entry.meta.value(QStringLiteral("template_id")).toString();
        if (!templateId.isEmpty()) {
            body << tr("Template: %1").arg(templateId);
        }
        const QJsonObject metrics = entry.meta.value(QStringLiteral("metrics")).toObject();
        if (metrics.contains(QStringLiteral("accuracy"))) {
            body << tr("Accuracy: %1")
                        .arg(metrics.value(QStringLiteral("accuracy")).toDouble(), 0, 'f', 3);
        }
        body << tr("Publish status: %1")
                    .arg(entry.meta.value(QStringLiteral("publish_status"))
                             .toString(QStringLiteral("unpublished")));
    } else {
        body << tr("Imported dataset file under datasets/.");
    }

    body << tr("Visibility: private (local only).");
    detailBody_->setText(body.join(QLatin1Char('\n')));

    // Placeholders stay disabled — wire cloud later.
    detailShareButton_->setEnabled(false);
    detailPublishButton_->setEnabled(false);
    detailShareButton_->setToolTip(tr("Sharing is a placeholder."));
    detailPublishButton_->setToolTip(tr("Cloud publish is a placeholder."));
}

void HubPage::clearDetail()
{
    selectedKey_.clear();
    detailTitle_->setText(tr("No selection"));
    detailMeta_->setText(tr("Pick an item in the local library to inspect it."));
    detailBody_->setText(
        tr("Plans live in plans/, datasets in datasets/, exported models in models/."));
    detailShareButton_->setEnabled(false);
    detailPublishButton_->setEnabled(false);
}

void HubPage::onSharePlaceholder()
{
    QMessageBox::information(
        this,
        tr("Sharing"),
        tr("Sharing to Hugging Face, Kaggle, orgs, and public/private visibility are placeholders. "
           "Items remain local under your project folder."));
}

void HubPage::onPublishPlaceholder()
{
    QMessageBox::information(
        this,
        tr("Cloud publish"),
        tr("Cloud publish is a placeholder. Exported models stay under models/ on this computer."));
}

void HubPage::onSignInPlaceholder()
{
    QMessageBox::information(
        this,
        tr("Sign in"),
        tr("Cloud sign-in is not available yet. The Hub indexes only your local project folder."));
}

QString HubPage::formatSize(qint64 bytes)
{
    if (bytes < 1024) {
        return QObject::tr("%1 B").arg(bytes);
    }
    if (bytes < 1024 * 1024) {
        return QObject::tr("%1 KB").arg(bytes / 1024.0, 0, 'f', 1);
    }
    if (bytes < 1024LL * 1024 * 1024) {
        return QObject::tr("%1 MB").arg(bytes / (1024.0 * 1024.0), 0, 'f', 1);
    }
    return QObject::tr("%1 GB").arg(bytes / (1024.0 * 1024.0 * 1024.0), 0, 'f', 2);
}

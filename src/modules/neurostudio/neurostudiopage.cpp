#include "modules/neurostudio/neurostudiopage.hpp"

#include "core/projectdir.hpp"
#include "core/studiodataset.hpp"
#include "core/theme.hpp"
#include "widgets/icons.hpp"
#include "widgets/pageheader.hpp"

#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFontMetrics>
#include <QFrame>
#include <QHBoxLayout>
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

NeuroStudioPage::NeuroStudioPage(QWidget *parent)
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

    layout->addWidget(header);
    layout->addSpacing(16);
    layout->addWidget(datasetLabel);
    layout->addSpacing(6);
    layout->addWidget(datasetStack_);
    layout->addSpacing(16);
    layout->addStretch(1);

    scroll->setWidget(content);
    rootLayout->addWidget(scroll);

    connect(&Theme::instance(), &Theme::changed, this, &NeuroStudioPage::refreshIcons);
    refreshIcons();
    setDatasetIdle();
}

QString NeuroStudioPage::currentDatasetPath() const
{
    return datasetPath_;
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
}

void NeuroStudioPage::setDatasetIdle()
{
    datasetStack_->setCurrentIndex(0);
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

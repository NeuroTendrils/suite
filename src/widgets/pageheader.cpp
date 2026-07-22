#include "widgets/pageheader.hpp"

#include <QLabel>
#include <QVBoxLayout>

PageHeader::PageHeader(const QString &title, const QString &subtitle, QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(4);

    auto *titleLabel = new QLabel(title, this);
    titleLabel->setObjectName(QStringLiteral("pageTitle"));

    auto *subtitleLabel = new QLabel(subtitle, this);
    subtitleLabel->setObjectName(QStringLiteral("pageDescription"));
    subtitleLabel->setWordWrap(true);

    layout->addWidget(titleLabel);
    layout->addWidget(subtitleLabel);
}

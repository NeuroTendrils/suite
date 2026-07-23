#include "widgets/pageheader.hpp"

#include <QLabel>
#include <QSizePolicy>
#include <QVBoxLayout>

PageHeader::PageHeader(const QString &title, const QString &subtitle, QWidget *parent)
    : QWidget(parent)
{
    setMinimumWidth(0);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(4);

    auto *titleLabel = new QLabel(title, this);
    titleLabel->setObjectName(QStringLiteral("pageTitle"));
    titleLabel->setMinimumWidth(0);
    titleLabel->setWordWrap(true);

    auto *subtitleLabel = new QLabel(subtitle, this);
    subtitleLabel->setObjectName(QStringLiteral("pageDescription"));
    subtitleLabel->setMinimumWidth(0);
    subtitleLabel->setWordWrap(true);
    subtitleLabel->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

    layout->addWidget(titleLabel);
    layout->addWidget(subtitleLabel);
}

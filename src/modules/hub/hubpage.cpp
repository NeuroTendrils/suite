#include "modules/hub/hubpage.hpp"

#include <QFont>
#include <QLabel>
#include <QVBoxLayout>

HubPage::HubPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(32, 32, 32, 32);

    auto *title = new QLabel(tr("NeuroTendrils Hub"), this);
    QFont titleFont = title->font();
    titleFont.setPointSize(24);
    titleFont.setBold(true);
    title->setFont(titleFont);

    auto *description =
        new QLabel(tr("Browse plans, datasets, and models stored on this computer."), this);
    description->setWordWrap(true);

    layout->addWidget(title);
    layout->addWidget(description);
    layout->addStretch();
}

#include "modules/hub/hubpage.hpp"

#include "widgets/pageheader.hpp"

#include <QVBoxLayout>

HubPage::HubPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("NeuroTendrils Hub"),
        tr("Browse plans, datasets, and models stored on this computer."), this);

    layout->addWidget(header);
    layout->addStretch();
}

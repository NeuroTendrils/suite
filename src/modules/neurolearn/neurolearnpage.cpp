#include "modules/neurolearn/neurolearnpage.hpp"

#include "widgets/pageheader.hpp"

#include <QVBoxLayout>

NeurolearnPage::NeurolearnPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("Neurolearn"), tr("Learn EEG and BCI concepts through guided demonstrations."), this);

    layout->addWidget(header);
    layout->addStretch();
}

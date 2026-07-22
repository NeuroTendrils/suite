#include "modules/neuroflow/neuroflowpage.hpp"

#include "widgets/pageheader.hpp"

#include <QVBoxLayout>

NeuroflowPage::NeuroflowPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("Neuroflow"), tr("Build and run reproducible EEG preprocessing plans."), this);

    layout->addWidget(header);
    layout->addStretch();
}

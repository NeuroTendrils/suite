#include "modules/neurostudio/neurostudiopage.hpp"

#include "widgets/pageheader.hpp"

#include <QVBoxLayout>

NeurostudioPage::NeurostudioPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("Neurostudio"), tr("Configure templates, train models, and inspect metrics."), this);

    layout->addWidget(header);
    layout->addStretch();
}

#include "modules/neuroflow/neuroflowpage.hpp"

#include <QFont>
#include <QLabel>
#include <QVBoxLayout>

NeuroflowPage::NeuroflowPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(32, 32, 32, 32);

    auto *title = new QLabel(tr("Neuroflow"), this);
    QFont titleFont = title->font();
    titleFont.setPointSize(24);
    titleFont.setBold(true);
    title->setFont(titleFont);

    auto *description =
        new QLabel(tr("Build and run reproducible EEG preprocessing plans."), this);
    description->setWordWrap(true);

    layout->addWidget(title);
    layout->addWidget(description);
    layout->addStretch();
}

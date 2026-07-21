#include "modules/neurolearn/neurolearnpage.hpp"

#include <QFont>
#include <QLabel>
#include <QVBoxLayout>

NeurolearnPage::NeurolearnPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(32, 32, 32, 32);

    auto *title = new QLabel(tr("Neurolearn"), this);
    QFont titleFont = title->font();
    titleFont.setPointSize(24);
    titleFont.setBold(true);
    title->setFont(titleFont);

    auto *description =
        new QLabel(tr("Learn EEG and BCI concepts through guided demonstrations."), this);
    description->setWordWrap(true);

    layout->addWidget(title);
    layout->addWidget(description);
    layout->addStretch();
}

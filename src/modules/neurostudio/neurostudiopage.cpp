#include "modules/neurostudio/neurostudiopage.hpp"

#include <QFont>
#include <QLabel>
#include <QVBoxLayout>

NeurostudioPage::NeurostudioPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(32, 32, 32, 32);

    auto *title = new QLabel(tr("Neurostudio"), this);
    QFont titleFont = title->font();
    titleFont.setPointSize(24);
    titleFont.setBold(true);
    title->setFont(titleFont);

    auto *description =
        new QLabel(tr("Configure templates, train models, and inspect metrics."), this);
    description->setWordWrap(true);

    layout->addWidget(title);
    layout->addWidget(description);
    layout->addStretch();
}

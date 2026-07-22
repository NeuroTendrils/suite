#include "modules/neurostudio/neurostudiopage.hpp"

#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QHBoxLayout>
#include <QVBoxLayout>

NeurostudioPage::NeurostudioPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("Neurostudio"), tr("Configure templates, train models, and inspect metrics."), this);

    // Placeholder until templates and the run view land (Phases 5-7).
    auto *cards = new QWidget(this);
    auto *cardsLayout = new QHBoxLayout(cards);
    cardsLayout->setContentsMargins(0, 0, 0, 0);
    cardsLayout->setSpacing(16);
    for (int i = 0; i < 3; ++i) {
        auto *card = new SkeletonLoader(cards);
        card->addBlock(1.0, 110);
        card->addBlock(0.7, 14);
        cardsLayout->addWidget(card);
    }

    auto *rows = new SkeletonLoader(this);
    rows->addBlock(0.5, 14);
    rows->addBlock(0.8, 14);

    layout->addWidget(header);
    layout->addSpacing(24);
    layout->addWidget(cards);
    layout->addSpacing(20);
    layout->addWidget(rows);
    layout->addStretch();
}

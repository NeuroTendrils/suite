#include "modules/neurolearn/neurolearnpage.hpp"

#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QVBoxLayout>

NeurolearnPage::NeurolearnPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("Neurolearn"), tr("Learn EEG and BCI concepts through guided demonstrations."), this);

    // Placeholder until lessons and the demo visualization land (Phase 8).
    auto *skeleton = new SkeletonLoader(this);
    skeleton->addBlock(1.0, 72);
    skeleton->addBlock(1.0, 72);
    skeleton->addBlock(1.0, 72);

    layout->addWidget(header);
    layout->addSpacing(24);
    layout->addWidget(skeleton);
    layout->addStretch();
}

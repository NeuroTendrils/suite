#include "modules/hub/hubpage.hpp"

#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QVBoxLayout>

HubPage::HubPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("NeuroTendrils Hub"),
        tr("Browse plans, datasets, and models stored on this computer."), this);

    // Placeholder until the local library index lands (Phase 9).
    auto *skeleton = new SkeletonLoader(this);
    skeleton->addBlock(0.3, 16);
    skeleton->addBlock(1.0, 52);
    skeleton->addBlock(1.0, 52);
    skeleton->addBlock(1.0, 52);
    skeleton->addBlock(1.0, 52);

    layout->addWidget(header);
    layout->addSpacing(24);
    layout->addWidget(skeleton);
    layout->addStretch();
}

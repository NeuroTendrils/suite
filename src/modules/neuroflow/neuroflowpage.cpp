#include "modules/neuroflow/neuroflowpage.hpp"

#include "widgets/pageheader.hpp"
#include "widgets/skeletonloader.hpp"

#include <QVBoxLayout>

NeuroflowPage::NeuroflowPage(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);

    auto *header = new PageHeader(
        tr("Neuroflow"), tr("Build and run reproducible EEG preprocessing plans."), this);

    // Placeholder until the file picker and step plan land (Phases 2-4).
    auto *skeleton = new SkeletonLoader(this);
    skeleton->addBlock(0.35, 18);
    skeleton->addBlock(1.0, 96);
    skeleton->addBlock(0.6, 14);
    skeleton->addBlock(0.8, 14);
    skeleton->addBlock(0.7, 14);

    layout->addWidget(header);
    layout->addSpacing(24);
    layout->addWidget(skeleton);
    layout->addStretch();
}

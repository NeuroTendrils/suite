#include "mainwindow.hpp"

#include "modules/hub/hubpage.hpp"
#include "modules/neuroflow/neuroflowpage.hpp"
#include "modules/neurolearn/neurolearnpage.hpp"
#include "modules/neurostudio/neurostudiopage.hpp"

#include <QHBoxLayout>
#include <QListWidget>
#include <QStackedWidget>
#include <QWidget>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , navigation_(new QListWidget(this))
    , pages_(new QStackedWidget(this))
{
    setWindowTitle(tr("NeuroTendrils"));
    resize(1024, 720);

    auto *centralWidget = new QWidget(this);
    auto *layout = new QHBoxLayout(centralWidget);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    navigation_->setAccessibleName(tr("Module navigation"));
    navigation_->setFixedWidth(200);
    navigation_->addItem(tr("Neuroflow"));
    navigation_->addItem(tr("Neurostudio"));
    navigation_->addItem(tr("Neurolearn"));
    navigation_->addItem(tr("Hub"));

    pages_->addWidget(new NeuroflowPage(pages_));
    pages_->addWidget(new NeurostudioPage(pages_));
    pages_->addWidget(new NeurolearnPage(pages_));
    pages_->addWidget(new HubPage(pages_));

    layout->addWidget(navigation_);
    layout->addWidget(pages_, 1);
    setCentralWidget(centralWidget);

    connect(navigation_,
            &QListWidget::currentRowChanged,
            pages_,
            &QStackedWidget::setCurrentIndex);

    navigation_->setCurrentRow(0);
}

MainWindow::~MainWindow() = default;

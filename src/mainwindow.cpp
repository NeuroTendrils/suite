#include "mainwindow.hpp"

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setWindowTitle(tr("NeuroTendrils"));
    resize(1024, 720);
}

MainWindow::~MainWindow() = default;

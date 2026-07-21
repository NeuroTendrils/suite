#include <QApplication>

#include "mainwindow.hpp"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    QApplication::setApplicationName(QStringLiteral("NeuroTendrils"));
    QApplication::setOrganizationName(QStringLiteral("NeuroTendrils"));
    QApplication::setApplicationVersion(QStringLiteral("0.0.1"));

    MainWindow window;
    window.show();

    return app.exec();
}

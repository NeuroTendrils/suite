#include <QApplication>

#include "core/projectdir.hpp"
#include "core/pythonruntime.hpp"
#include "core/theme.hpp"
#include "mainwindow.hpp"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    QApplication::setApplicationName(QStringLiteral("NeuroTendrils"));
    QApplication::setOrganizationName(QStringLiteral("NeuroTendrils"));
    QApplication::setApplicationVersion(QStringLiteral("0.0.1"));

    Theme::instance().initialize(app);
    ProjectDir::instance().initialize();
    PythonRuntime::instance().initialize();

    MainWindow window;
    window.show();

    return app.exec();
}

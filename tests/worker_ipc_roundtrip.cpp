#include "core/pythonruntime.hpp"
#include "core/workerclient.hpp"

#include <QCoreApplication>
#include <QEventLoop>
#include <QJsonObject>
#include <QTimer>
#include <cstdio>

namespace
{
struct StepResult
{
    bool ok = false;
    QJsonObject result;
    QString errorCode;
    QString errorMessage;
};

StepResult runRequest(WorkerClient &client, const QString &cmd, const QJsonObject &args)
{
    StepResult out;
    QEventLoop loop;

    QObject::connect(
        &client,
        &WorkerClient::finished,
        &loop,
        [&](bool ok, const QJsonObject &result, const QString &errorCode,
            const QString &errorMessage) {
            out.ok = ok;
            out.result = result;
            out.errorCode = errorCode;
            out.errorMessage = errorMessage;
            loop.quit();
        });

    QTimer::singleShot(20000, &loop, &QEventLoop::quit);
    client.startRequest(QStringLiteral("neuroflow"), cmd, args, 15000);
    loop.exec();
    return out;
}
} // namespace

int main(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);
    QCoreApplication::setApplicationName(QStringLiteral("neurotendrils-ipc-roundtrip"));
    QCoreApplication::setOrganizationName(QStringLiteral("NeuroTendrils"));

    PythonRuntime::instance().initialize();
    if (!PythonRuntime::instance().isAvailable()) {
        std::fprintf(stderr, "FAIL: no Python interpreter found\n");
        return 1;
    }
    if (WorkerClient::workersRoot().isEmpty()) {
        std::fprintf(stderr, "FAIL: workers/ directory not found (run from suite root)\n");
        return 1;
    }

    WorkerClient client;

    const StepResult ping = runRequest(client, QStringLiteral("ping"), {});
    if (!ping.ok || !ping.result.value(QStringLiteral("pong")).toBool()) {
        std::fprintf(stderr, "FAIL: ping: %s (%s)\n",
                     qPrintable(ping.errorMessage),
                     qPrintable(ping.errorCode));
        return 1;
    }

    const StepResult echo = runRequest(
        client,
        QStringLiteral("echo"),
        QJsonObject{{QStringLiteral("hello"), QStringLiteral("suite")}});
    if (!echo.ok
        || echo.result.value(QStringLiteral("echo")).toObject().value(QStringLiteral("hello")).toString()
               != QStringLiteral("suite")) {
        std::fprintf(stderr, "FAIL: echo: %s (%s)\n",
                     qPrintable(echo.errorMessage),
                     qPrintable(echo.errorCode));
        return 1;
    }

    std::printf("OK: WorkerClient ping+echo round-trip\n");
    return 0;
}

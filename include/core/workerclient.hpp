#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QStringList>

class QProcess;
class QTimer;

// Launches Python science workers via QProcess
// and speaks the nt_ipc JSON-lines protocol over stdio.
class WorkerClient final : public QObject
{
    Q_OBJECT

public:
    explicit WorkerClient(QObject *parent = nullptr);
    ~WorkerClient() override;

    [[nodiscard]] bool isBusy() const;

    // One-shot: python -m <module> <moduleArgs...>
    // Expects a single JSON object on stdout (legacy ping or full envelope).
    void start(const QString &module,
               const QStringList &moduleArgs = {},
               int timeoutMs = 30000);

    // Preferred: python -m <module> ipc
    // Writes one request line to stdin; emits events until a final response.
    void startRequest(const QString &module,
                      const QString &cmd,
                      const QJsonObject &args = {},
                      int timeoutMs = 30000);

    void cancel();

    // Resolves the workers/ directory (repo / app adjacent). Empty if missing.
    [[nodiscard]] static QString workersRoot();

signals:
    void eventReceived(const QString &requestId, const QString &name, const QJsonObject &data);
    void finished(bool ok,
                  const QJsonObject &result,
                  const QString &errorCode,
                  const QString &errorMessage);
    void logMessage(const QString &redactedLine);

private:
    void launch(const QString &module, const QStringList &moduleArgs, int timeoutMs);
    void handleStdoutLine(const QString &line);
    void finishWithError(const QString &code, const QString &message);
    void finishSuccess(const QJsonObject &result);
    void onTimeout();
    void cleanupProcess();

    [[nodiscard]] static QStringList pythonPathEntries(const QString &workers);
    [[nodiscard]] QString nextRequestId();

    QProcess *process_ = nullptr;
    QTimer *timeoutTimer_ = nullptr;
    QString stdoutBuffer_;
    QString stderrBuffer_;
    QString activeRequestId_;
    bool expectingEnvelope_ = false;
    bool finished_ = false;
    int requestCounter_ = 0;
};

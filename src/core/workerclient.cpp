#include "core/workerclient.hpp"

#include "core/ipcredact.hpp"
#include "core/projectdir.hpp"
#include "core/pythonruntime.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QProcess>
#include <QProcessEnvironment>
#include <QTimer>
#include <QUuid>

WorkerClient::WorkerClient(QObject *parent)
    : QObject(parent)
    , timeoutTimer_(new QTimer(this))
{
    timeoutTimer_->setSingleShot(true);
    connect(timeoutTimer_, &QTimer::timeout, this, &WorkerClient::onTimeout);
}

WorkerClient::~WorkerClient()
{
    cancel();
}

bool WorkerClient::isBusy() const
{
    return process_ != nullptr && !finished_;
}

void WorkerClient::start(const QString &module, const QStringList &moduleArgs, int timeoutMs)
{
    if (isBusy()) {
        emit finished(false, {}, QStringLiteral("busy"),
                      QStringLiteral("A worker is already running."));
        return;
    }

    expectingEnvelope_ = false;
    activeRequestId_.clear();
    launch(module, moduleArgs, timeoutMs);
}

void WorkerClient::startRequest(const QString &module,
                                const QString &cmd,
                                const QJsonObject &args,
                                int timeoutMs)
{
    if (isBusy()) {
        emit finished(false, {}, QStringLiteral("busy"),
                      QStringLiteral("A worker is already running."));
        return;
    }

    expectingEnvelope_ = true;
    activeRequestId_ = nextRequestId();

    launch(module, {QStringLiteral("ipc")}, timeoutMs);
    if (process_ == nullptr || finished_) {
        return;
    }

    const QJsonObject request{
        {QStringLiteral("v"), 1},
        {QStringLiteral("id"), activeRequestId_},
        {QStringLiteral("cmd"), cmd},
        {QStringLiteral("args"), args},
    };

    const QByteArray line = QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n';
    emit logMessage(IpcRedact::redactText(QString::fromUtf8(line.trimmed())));
    process_->write(line);
    process_->closeWriteChannel();
}

void WorkerClient::cancel()
{
    if (process_ == nullptr) {
        return;
    }

    timeoutTimer_->stop();
    if (process_->state() != QProcess::NotRunning) {
        process_->kill();
        process_->waitForFinished(1000);
    }

    if (!finished_) {
        finishWithError(QStringLiteral("cancelled"), QStringLiteral("Worker cancelled."));
    } else {
        cleanupProcess();
    }
}

QString WorkerClient::workersRoot()
{
    QStringList candidates;

    const QString appDir = QCoreApplication::applicationDirPath();
    candidates << QDir(appDir).filePath(QStringLiteral("workers"));
    candidates << QDir(appDir).filePath(QStringLiteral("../workers"));
    candidates << QDir(appDir).filePath(QStringLiteral("../../workers"));
    candidates << QDir(appDir).filePath(QStringLiteral("../../../workers"));
    candidates << QDir(appDir).filePath(QStringLiteral("../../../../workers"));

    QDir cwd = QDir::current();
    for (int i = 0; i < 5; ++i) {
        candidates << cwd.filePath(QStringLiteral("workers"));
        if (!cwd.cdUp()) {
            break;
        }
    }

    candidates.removeDuplicates();
    for (const QString &candidate : candidates) {
        const QDir dir(candidate);
        if (dir.exists() && QFileInfo::exists(dir.filePath(QStringLiteral("neuroflow")))) {
            return QDir::cleanPath(dir.absolutePath());
        }
    }
    return {};
}

void WorkerClient::launch(const QString &module, const QStringList &moduleArgs, int timeoutMs)
{
    cleanupProcess();
    finished_ = false;
    stdoutBuffer_.clear();
    stderrBuffer_.clear();

    const PythonRuntime &python = PythonRuntime::instance();
    if (!python.isAvailable()) {
        finishWithError(QStringLiteral("python_unavailable"),
                        QStringLiteral("No Python interpreter found. Run python/setup_venv.sh."));
        return;
    }

    const QString workers = workersRoot();
    if (workers.isEmpty()) {
        finishWithError(QStringLiteral("workers_missing"),
                        QStringLiteral("Could not locate the workers/ directory."));
        return;
    }

    if (module.trimmed().isEmpty()) {
        finishWithError(QStringLiteral("invalid_module"), QStringLiteral("Worker module is empty."));
        return;
    }

    QStringList arguments;
    arguments << QStringLiteral("-m") << module;
    arguments.append(moduleArgs);

    process_ = new QProcess(this);
    process_->setProgram(python.interpreterPath());
    process_->setArguments(arguments);
    process_->setProcessChannelMode(QProcess::SeparateChannels);

    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QStringList pathEntries = pythonPathEntries(workers);
    const QString pathSep =
#ifdef Q_OS_WIN
        QStringLiteral(";");
#else
        QStringLiteral(":");
#endif
    const QString existing = env.value(QStringLiteral("PYTHONPATH"));
    QString pythonPath = pathEntries.join(pathSep);
    if (!existing.isEmpty()) {
        pythonPath += pathSep + existing;
    }
    env.insert(QStringLiteral("PYTHONPATH"), pythonPath);
    env.insert(QStringLiteral("PYTHONUNBUFFERED"), QStringLiteral("1"));
    env.insert(QStringLiteral("NEUROTENDRILS_PROJECT"), ProjectDir::instance().root());
    process_->setProcessEnvironment(env);
    process_->setWorkingDirectory(ProjectDir::instance().root().isEmpty()
                                      ? QDir::currentPath()
                                      : ProjectDir::instance().root());

    connect(process_, &QProcess::readyReadStandardOutput, this, [this] {
        stdoutBuffer_.append(QString::fromUtf8(process_->readAllStandardOutput()));
        int newline = stdoutBuffer_.indexOf(QLatin1Char('\n'));
        while (newline >= 0) {
            const QString line = stdoutBuffer_.left(newline);
            stdoutBuffer_.remove(0, newline + 1);
            handleStdoutLine(line);
            newline = stdoutBuffer_.indexOf(QLatin1Char('\n'));
        }
    });

    connect(process_, &QProcess::readyReadStandardError, this, [this] {
        stderrBuffer_.append(QString::fromUtf8(process_->readAllStandardError()));
        int newline = stderrBuffer_.indexOf(QLatin1Char('\n'));
        while (newline >= 0) {
            const QString line = stderrBuffer_.left(newline).trimmed();
            stderrBuffer_.remove(0, newline + 1);
            if (!line.isEmpty()) {
                emit logMessage(IpcRedact::redactText(line));
            }
            newline = stderrBuffer_.indexOf(QLatin1Char('\n'));
        }
    });

    connect(process_,
            QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this,
            [this](int exitCode, QProcess::ExitStatus status) {
                if (finished_) {
                    cleanupProcess();
                    return;
                }

                // Flush partial buffers.
                if (!stdoutBuffer_.trimmed().isEmpty()) {
                    handleStdoutLine(stdoutBuffer_);
                    stdoutBuffer_.clear();
                }
                if (!stderrBuffer_.trimmed().isEmpty()) {
                    emit logMessage(IpcRedact::redactText(stderrBuffer_.trimmed()));
                    stderrBuffer_.clear();
                }

                if (finished_) {
                    cleanupProcess();
                    return;
                }

                if (status != QProcess::NormalExit || exitCode != 0) {
                    finishWithError(QStringLiteral("worker_exit"),
                                    QStringLiteral("Worker exited with code %1.").arg(exitCode));
                } else if (expectingEnvelope_) {
                    finishWithError(QStringLiteral("incomplete_response"),
                                    QStringLiteral("Worker exited before a final response."));
                } else {
                    finishWithError(QStringLiteral("empty_response"),
                                    QStringLiteral("Worker produced no JSON response."));
                }
            });

    emit logMessage(QStringLiteral("Starting worker: %1 -m %2 %3")
                        .arg(QFileInfo(python.interpreterPath()).fileName(),
                             module,
                             moduleArgs.join(QLatin1Char(' ')))
                        .trimmed());

    process_->start();
    if (!process_->waitForStarted(3000)) {
        finishWithError(QStringLiteral("start_failed"),
                        QStringLiteral("Failed to start worker process."));
        return;
    }

    if (timeoutMs > 0) {
        timeoutTimer_->start(timeoutMs);
    }
}

void WorkerClient::handleStdoutLine(const QString &line)
{
    const QString trimmed = line.trimmed();
    if (trimmed.isEmpty() || finished_) {
        return;
    }

    emit logMessage(IpcRedact::redactText(trimmed));

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(trimmed.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
        if (expectingEnvelope_) {
            return; // ignore non-JSON noise while streaming
        }
        finishWithError(QStringLiteral("invalid_json"),
                        QStringLiteral("Worker stdout was not valid JSON."));
        return;
    }

    const QJsonObject object = doc.object();

    if (object.value(QStringLiteral("type")).toString() == QStringLiteral("event")) {
        emit eventReceived(object.value(QStringLiteral("id")).toString(),
                           object.value(QStringLiteral("name")).toString(),
                           object.value(QStringLiteral("data")).toObject());
        return;
    }

    if (object.contains(QStringLiteral("ok"))) {
        const QString id = object.value(QStringLiteral("id")).toString();
        if (expectingEnvelope_ && !activeRequestId_.isEmpty() && id != activeRequestId_) {
            return;
        }

        if (object.value(QStringLiteral("ok")).toBool()) {
            finishSuccess(object.value(QStringLiteral("result")).toObject());
        } else {
            const QJsonObject error = object.value(QStringLiteral("error")).toObject();
            finishWithError(error.value(QStringLiteral("code")).toString(QStringLiteral("worker_error")),
                            error.value(QStringLiteral("message"))
                                .toString(QStringLiteral("Worker reported an error.")));
        }
        return;
    }

    // Legacy one-shot payloads (e.g. neuroflow ping) without a full envelope.
    if (!expectingEnvelope_) {
        finishSuccess(object);
    }
}

void WorkerClient::finishWithError(const QString &code, const QString &message)
{
    if (finished_) {
        return;
    }
    finished_ = true;
    timeoutTimer_->stop();

    if (process_ != nullptr && process_->state() != QProcess::NotRunning) {
        process_->kill();
        process_->waitForFinished(1000);
    }

    emit logMessage(QStringLiteral("Worker error [%1]: %2").arg(code, message));
    emit finished(false, {}, code, message);
    cleanupProcess();
}

void WorkerClient::finishSuccess(const QJsonObject &result)
{
    if (finished_) {
        return;
    }
    finished_ = true;
    timeoutTimer_->stop();

    if (process_ != nullptr && process_->state() != QProcess::NotRunning) {
        process_->kill();
        process_->waitForFinished(1000);
    }

    emit finished(true, result, {}, {});
    cleanupProcess();
}

void WorkerClient::onTimeout()
{
    finishWithError(QStringLiteral("timeout"), QStringLiteral("Worker timed out."));
}

void WorkerClient::cleanupProcess()
{
    if (process_ == nullptr) {
        return;
    }
    process_->disconnect(this);
    process_->deleteLater();
    process_ = nullptr;
}

QStringList WorkerClient::pythonPathEntries(const QString &workers)
{
    return {
        QDir(workers).filePath(QStringLiteral("_shared")),
        QDir(workers).filePath(QStringLiteral("neuroflow")),
    };
}

QString WorkerClient::nextRequestId()
{
    ++requestCounter_;
    return QStringLiteral("req-%1-%2")
        .arg(requestCounter_)
        .arg(QUuid::createUuid().toString(QUuid::WithoutBraces).left(8));
}

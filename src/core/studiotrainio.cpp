#include "core/studiotrainio.hpp"

#include "core/projectdir.hpp"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>

namespace
{

QString sanitizeBaseName(const QString &preferredBaseName)
{
    QString base = preferredBaseName.trimmed();
    if (base.isEmpty()) {
        base = QStringLiteral("train");
    }
    QString sanitized;
    sanitized.reserve(base.size());
    for (const QChar ch : base) {
        if (ch.isLetterOrNumber() || ch == QLatin1Char('_') || ch == QLatin1Char('-')) {
            sanitized.append(ch);
        } else {
            sanitized.append(QLatin1Char('_'));
        }
    }
    return sanitized.isEmpty() ? QStringLiteral("train") : sanitized;
}

} // namespace

namespace StudioTrainIo
{

Paths suggestPaths(const QString &preferredBaseName)
{
    Paths paths;
    const QString runsRoot = ProjectDir::instance().runsDir();
    if (runsRoot.isEmpty()) {
        return paths;
    }

    QDir runs(runsRoot);
    runs.mkpath(QStringLiteral("."));

    const QString stamp =
        QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd_HHmmss"));
    QString folder =
        QStringLiteral("studio_%1_%2").arg(sanitizeBaseName(preferredBaseName), stamp);

    int attempt = 1;
    while (runs.exists(folder)) {
        folder = QStringLiteral("studio_%1_%2_%3")
                     .arg(sanitizeBaseName(preferredBaseName), stamp)
                     .arg(attempt);
        ++attempt;
    }

    paths.runDir = runs.filePath(folder);
    QDir().mkpath(paths.runDir);
    paths.checkpointPath = QDir(paths.runDir).filePath(QStringLiteral("checkpoint.pt"));
    paths.metricsPath = QDir(paths.runDir).filePath(QStringLiteral("metrics.json"));
    paths.trainMetaPath = QDir(paths.runDir).filePath(QStringLiteral("train.json"));
    return paths;
}

} // namespace StudioTrainIo

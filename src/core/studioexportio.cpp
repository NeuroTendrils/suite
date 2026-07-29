#include "core/studioexportio.hpp"

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
        base = QStringLiteral("model");
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
    return sanitized.isEmpty() ? QStringLiteral("model") : sanitized;
}

} // namespace

namespace StudioExportIo
{

Paths suggestPaths(const QString &preferredBaseName)
{
    Paths paths;
    const QString modelsRoot = ProjectDir::instance().modelsDir();
    if (modelsRoot.isEmpty()) {
        return paths;
    }

    QDir models(modelsRoot);
    models.mkpath(QStringLiteral("."));

    const QString stamp =
        QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd_HHmmss"));
    QString folder =
        QStringLiteral("%1_%2").arg(sanitizeBaseName(preferredBaseName), stamp);

    int attempt = 1;
    while (models.exists(folder)) {
        folder = QStringLiteral("%1_%2_%3")
                     .arg(sanitizeBaseName(preferredBaseName), stamp)
                     .arg(attempt);
        ++attempt;
    }

    paths.modelDir = models.filePath(folder);
    QDir().mkpath(paths.modelDir);
    paths.metadataPath = QDir(paths.modelDir).filePath(QStringLiteral("model.json"));
    return paths;
}

} // namespace StudioExportIo

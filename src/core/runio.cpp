#include "core/runio.hpp"

#include "core/plangenerator.hpp"
#include "core/projectdir.hpp"
#include "core/reprometa.hpp"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonDocument>

namespace
{

QString resolvePath(const QString &path)
{
    const QString cleaned = QDir::cleanPath(QFileInfo(path).absoluteFilePath());
    const QFileInfo info(cleaned);
    const QString canonical = info.canonicalFilePath();
    return canonical.isEmpty() ? cleaned : canonical;
}

bool isUnderRunsDir(const QString &path)
{
    const QString runs = ProjectDir::instance().runsDir();
    if (runs.isEmpty() || path.isEmpty()) {
        return false;
    }

    const QString resolved = resolvePath(path);
    const QString resolvedRuns = resolvePath(runs);

#ifdef Q_OS_WIN
    constexpr Qt::CaseSensitivity caseSensitivity = Qt::CaseInsensitive;
#else
    constexpr Qt::CaseSensitivity caseSensitivity = Qt::CaseSensitive;
#endif

    return resolved.compare(resolvedRuns, caseSensitivity) == 0
           || resolved.startsWith(resolvedRuns + QLatin1Char('/'), caseSensitivity);
}

QString sanitizeBaseName(const QString &preferredBaseName)
{
    QString base = preferredBaseName.trimmed();
    if (base.isEmpty()) {
        base = QStringLiteral("run");
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
    return sanitized.isEmpty() ? QStringLiteral("run") : sanitized;
}

} // namespace

namespace RunIo
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
    QString folder = QStringLiteral("%1_%2").arg(sanitizeBaseName(preferredBaseName), stamp);

    int attempt = 1;
    while (runs.exists(folder)) {
        folder = QStringLiteral("%1_%2_%3")
                     .arg(sanitizeBaseName(preferredBaseName), stamp)
                     .arg(attempt);
        ++attempt;
    }

    paths.runDir = runs.filePath(folder);
    QDir().mkpath(paths.runDir);
    paths.outputPath = QDir(paths.runDir).filePath(QStringLiteral("cleaned.fif"));
    paths.metadataPath = QDir(paths.runDir).filePath(QStringLiteral("run.json"));
    return paths;
}

Result writeMetadata(const QString &metadataPath,
                     const QString &inputPath,
                     const QString &outputPath,
                     const PlanGenerator::Plan &plan,
                     const QString &planPath,
                     const QJsonObject &workerResult)
{
    Result result;
    result.path = metadataPath;

    if (ProjectDir::instance().root().isEmpty()) {
        result.error = QStringLiteral("No project folder configured.");
        return result;
    }
    if (metadataPath.trimmed().isEmpty()) {
        result.error = QStringLiteral("No metadata path.");
        return result;
    }
    if (!isUnderRunsDir(metadataPath)) {
        result.error = QStringLiteral("Run metadata must be saved inside the project runs/ folder.");
        return result;
    }

    QJsonObject document{
        {QStringLiteral("v"), 1},
        {QStringLiteral("saved_at"),
         QDateTime::currentDateTimeUtc().toString(Qt::ISODate)},
        {QStringLiteral("input_path"), inputPath},
        {QStringLiteral("output_path"), outputPath},
        {QStringLiteral("plan"), PlanGenerator::toJson(plan)},
        {QStringLiteral("result"), workerResult},
    };
    if (!planPath.isEmpty()) {
        document.insert(QStringLiteral("plan_path"), planPath);
    }

    // Prefer the worker's full reproducibility block; fall back to plan stamp.
    if (workerResult.contains(QStringLiteral("reproducibility"))) {
        document.insert(QStringLiteral("reproducibility"),
                        workerResult.value(QStringLiteral("reproducibility")));
    } else {
        document.insert(QStringLiteral("reproducibility"), ReproMeta::planStamp());
    }

    QDir().mkpath(QFileInfo(metadataPath).absolutePath());
    QFile file(metadataPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
        result.error = QStringLiteral("Could not write run metadata.");
        return result;
    }

    const QByteArray bytes = QJsonDocument(document).toJson(QJsonDocument::Indented);
    if (file.write(bytes) != bytes.size()) {
        result.error = QStringLiteral("Failed while writing run metadata.");
        return result;
    }

    result.ok = true;
    result.path = QFileInfo(metadataPath).absoluteFilePath();
    return result;
}

} // namespace RunIo

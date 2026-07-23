#include "core/datasetimport.hpp"

#include "core/projectdir.hpp"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>

namespace
{
QString uniqueDestination(const QDir &datasets, const QString &fileName)
{
    const QFileInfo info(fileName);
    const QString base = info.completeBaseName();
    const QString suffix = info.suffix().isEmpty()
                               ? QString()
                               : QStringLiteral(".") + info.suffix();

    QString candidate = fileName;
    int attempt = 1;
    while (datasets.exists(candidate)) {
        candidate = QStringLiteral("%1_%2%3").arg(base).arg(attempt).arg(suffix);
        ++attempt;
    }
    return datasets.filePath(candidate);
}

bool suffixAllowed(const QString &path)
{
    const QString suffix = QFileInfo(path).suffix().toLower();
    // Handle .fif.gz style double suffixes loosely via fileName check.
    const QString name = QFileInfo(path).fileName().toLower();
    for (const QString &allowed : DatasetImport::allowedSuffixes()) {
        if (name.endsWith(QStringLiteral(".") + allowed) || suffix == allowed) {
            return true;
        }
    }
    return false;
}
} // namespace

namespace DatasetImport
{

QStringList allowedSuffixes()
{
    return {
        QStringLiteral("edf"),
        QStringLiteral("bdf"),
        QStringLiteral("fif"),
        QStringLiteral("fif.gz"),
        QStringLiteral("set"),
        QStringLiteral("vhdr"),
        QStringLiteral("eeg"),
        QStringLiteral("cnt"),
        QStringLiteral("mff"),
        QStringLiteral("gdf"),
    };
}

QStringList fileFilters()
{
    return {
        QStringLiteral("EEG recordings (*.edf *.bdf *.fif *.fif.gz *.set *.vhdr *.eeg *.cnt *.mff *.gdf)"),
        QStringLiteral("All files (*)"),
    };
}

Result importRecording(const QString &sourcePath)
{
    Result result;
    result.sourcePath = sourcePath;

    if (sourcePath.trimmed().isEmpty()) {
        result.error = QStringLiteral("No file selected.");
        return result;
    }

    const QFileInfo sourceInfo(sourcePath);
    if (!sourceInfo.exists() || !sourceInfo.isFile()) {
        result.error = QStringLiteral("Selected path is not a readable file.");
        return result;
    }
    if (!suffixAllowed(sourcePath)) {
        result.error = QStringLiteral("Unsupported recording type.");
        return result;
    }

    ProjectDir &project = ProjectDir::instance();
    if (project.root().isEmpty()) {
        result.error = QStringLiteral("Project folder is not configured.");
        return result;
    }

    const QString datasets = project.datasetsDir();
    QDir().mkpath(datasets);

    // Already inside the sandbox: use in place (reference / no copy).
    if (project.contains(sourcePath)) {
        result.ok = true;
        result.copied = false;
        result.datasetPath = QFileInfo(sourcePath).absoluteFilePath();
        if (!project.contains(result.datasetPath)) {
            result.ok = false;
            result.error = QStringLiteral("Resolved path escapes the project folder.");
            result.datasetPath.clear();
        }
        return result;
    }

    const QString destination = uniqueDestination(QDir(datasets), sourceInfo.fileName());
    if (!QFile::copy(sourcePath, destination)) {
        result.error = QStringLiteral("Failed to copy recording into datasets/.");
        return result;
    }

    if (!project.contains(destination)) {
        QFile::remove(destination);
        result.error = QStringLiteral("Import rejected: destination outside project sandbox.");
        return result;
    }

    result.ok = true;
    result.copied = true;
    result.datasetPath = QFileInfo(destination).absoluteFilePath();
    return result;
}

} // namespace DatasetImport

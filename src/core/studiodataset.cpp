#include "core/studiodataset.hpp"

#include "core/projectdir.hpp"

#include <QDir>
#include <QFileInfo>

namespace
{

bool suffixAllowed(const QString &path)
{
    const QString name = QFileInfo(path).fileName().toLower();
    const QString suffix = QFileInfo(path).suffix().toLower();
    for (const QString &allowed : StudioDataset::allowedSuffixes()) {
        if (name.endsWith(QStringLiteral(".") + allowed) || suffix == allowed) {
            return true;
        }
    }
    return false;
}

QString kindForPath(const QString &absolutePath)
{
    const ProjectDir &project = ProjectDir::instance();
    const QString cleaned = QDir::cleanPath(absolutePath);

    const QString runs = QDir::cleanPath(project.runsDir());
    if (!runs.isEmpty()
        && (cleaned == runs || cleaned.startsWith(runs + QLatin1Char('/')))) {
        return QStringLiteral("run_output");
    }

    const QString datasets = QDir::cleanPath(project.datasetsDir());
    if (!datasets.isEmpty()
        && (cleaned == datasets || cleaned.startsWith(datasets + QLatin1Char('/')))) {
        return QStringLiteral("dataset");
    }

    return QStringLiteral("project_file");
}

} // namespace

namespace StudioDataset
{

QStringList allowedSuffixes()
{
    // Cleaned Flow outputs are usually .fif; also accept common raw types in datasets/.
    return {
        QStringLiteral("fif"),
        QStringLiteral("fif.gz"),
        QStringLiteral("edf"),
        QStringLiteral("bdf"),
        QStringLiteral("set"),
        QStringLiteral("gdf"),
    };
}

QStringList fileFilters()
{
    return {
        QStringLiteral(
            "EEG / cleaned data (*.fif *.fif.gz *.edf *.bdf *.set *.gdf)"),
        QStringLiteral("All files (*)"),
    };
}

QString preferredStartDir()
{
    const ProjectDir &project = ProjectDir::instance();
    if (project.root().isEmpty()) {
        return {};
    }

    const QString runs = project.runsDir();
    if (QDir(runs).exists()) {
        return runs;
    }
    const QString datasets = project.datasetsDir();
    if (QDir(datasets).exists()) {
        return datasets;
    }
    return project.root();
}

Result selectPath(const QString &sourcePath)
{
    Result result;

    if (sourcePath.trimmed().isEmpty()) {
        result.error = QStringLiteral("No path selected.");
        return result;
    }

    ProjectDir &project = ProjectDir::instance();
    if (project.root().isEmpty()) {
        result.error = QStringLiteral("Project folder is not configured.");
        return result;
    }

    if (!project.contains(sourcePath)) {
        result.error = QStringLiteral(
            "Training data must be inside the project folder. "
            "Run NeuroFlow first, or import a recording into datasets/.");
        return result;
    }

    QFileInfo info(sourcePath);
    QString resolved;

    if (info.isDir()) {
        // Allow picking a runs/<id>/ folder that contains cleaned.fif.
        const QDir dir(info.absoluteFilePath());
        const QString cleanedFif = dir.filePath(QStringLiteral("cleaned.fif"));
        if (!QFileInfo::exists(cleanedFif)) {
            result.error = QStringLiteral(
                "Folder has no cleaned.fif. Pick a NeuroFlow run folder or a data file.");
            return result;
        }
        resolved = QFileInfo(cleanedFif).absoluteFilePath();
    } else if (info.isFile()) {
        if (!suffixAllowed(sourcePath)) {
            result.error = QStringLiteral("Unsupported data type for Studio.");
            return result;
        }
        resolved = info.absoluteFilePath();
    } else {
        result.error = QStringLiteral("Selected path is not a readable file or folder.");
        return result;
    }

    if (!project.contains(resolved)) {
        result.error = QStringLiteral("Resolved path escapes the project folder.");
        return result;
    }

    result.ok = true;
    result.path = resolved;
    result.displayName = QFileInfo(resolved).fileName();
    result.kind = kindForPath(resolved);
    return result;
}

} // namespace StudioDataset

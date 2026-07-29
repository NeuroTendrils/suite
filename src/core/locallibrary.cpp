#include "core/locallibrary.hpp"

#include "core/modellibrary.hpp"
#include "core/projectdir.hpp"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>

namespace
{

QString formatModified(const QFileInfo &info)
{
    return info.lastModified().toUTC().toString(Qt::ISODate);
}

bool isDatasetSuffix(const QString &suffix, const QString &fileName)
{
    const QString lower = suffix.toLower();
    if (lower == QLatin1String("edf") || lower == QLatin1String("bdf")
        || lower == QLatin1String("fif") || lower == QLatin1String("set")
        || lower == QLatin1String("gdf") || lower == QLatin1String("vhdr")
        || lower == QLatin1String("eeg") || lower == QLatin1String("cnt")
        || lower == QLatin1String("mff")) {
        return true;
    }
    return fileName.endsWith(QLatin1String(".fif.gz"), Qt::CaseInsensitive);
}

QVector<LocalLibrary::Entry> scanPlans()
{
    QVector<LocalLibrary::Entry> entries;
    const QString root = ProjectDir::instance().plansDir();
    if (root.isEmpty()) {
        return entries;
    }
    const QDir dir(root);
    if (!dir.exists()) {
        return entries;
    }

    const QFileInfoList files =
        dir.entryInfoList({QStringLiteral("*.json")}, QDir::Files, QDir::Time);
    for (const QFileInfo &info : files) {
        if (!ProjectDir::instance().contains(info.absoluteFilePath())) {
            continue;
        }

        LocalLibrary::Entry entry;
        entry.kind = LocalLibrary::Kind::Plan;
        entry.id = info.completeBaseName();
        entry.path = info.absoluteFilePath();
        entry.sizeBytes = info.size();
        entry.modified = formatModified(info);
        entry.title = entry.id;

        QFile file(info.absoluteFilePath());
        if (file.open(QIODevice::ReadOnly)) {
            const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
            file.close();
            if (doc.isObject()) {
                entry.meta = doc.object();
                const QString name = entry.meta.value(QStringLiteral("name")).toString();
                if (!name.isEmpty()) {
                    entry.title = name;
                }
                const int stepCount = entry.meta.value(QStringLiteral("steps")).toArray().size();
                QStringList bits;
                bits << QObject::tr("%n step(s)", nullptr, stepCount);
                const QString dataset = entry.meta.value(QStringLiteral("dataset_path")).toString();
                if (!dataset.isEmpty()) {
                    bits << QFileInfo(dataset).fileName();
                }
                entry.subtitle = bits.join(QStringLiteral(" · "));
            }
        }
        if (entry.subtitle.isEmpty()) {
            entry.subtitle = QObject::tr("NeuroFlow plan");
        }
        entries.append(entry);
    }
    return entries;
}

QVector<LocalLibrary::Entry> scanDatasets()
{
    QVector<LocalLibrary::Entry> entries;
    const QString root = ProjectDir::instance().datasetsDir();
    if (root.isEmpty()) {
        return entries;
    }
    const QDir dir(root);
    if (!dir.exists()) {
        return entries;
    }

    const QFileInfoList files = dir.entryInfoList(QDir::Files, QDir::Time);
    for (const QFileInfo &info : files) {
        if (!isDatasetSuffix(info.suffix(), info.fileName())) {
            continue;
        }
        if (!ProjectDir::instance().contains(info.absoluteFilePath())) {
            continue;
        }

        LocalLibrary::Entry entry;
        entry.kind = LocalLibrary::Kind::Dataset;
        entry.id = info.fileName();
        entry.title = info.fileName();
        entry.path = info.absoluteFilePath();
        entry.sizeBytes = info.size();
        entry.modified = formatModified(info);
        entry.subtitle = info.suffix().isEmpty()
                             ? QObject::tr("Dataset")
                             : info.suffix().toUpper() + QObject::tr(" · dataset");
        entries.append(entry);
    }
    return entries;
}

QVector<LocalLibrary::Entry> scanModels()
{
    QVector<LocalLibrary::Entry> entries;
    const QVector<ModelLibrary::Entry> models = ModelLibrary::scan();
    for (const ModelLibrary::Entry &model : models) {
        LocalLibrary::Entry entry;
        entry.kind = LocalLibrary::Kind::Model;
        entry.id = model.id;
        entry.title = model.title;
        entry.path = model.modelDir;
        entry.modified = model.exportedAt;
        entry.meta = model.meta;
        QFileInfo artifact(model.artifactPath);
        if (artifact.exists()) {
            entry.sizeBytes = artifact.size();
        }

        QStringList bits;
        if (!model.formatLabel.isEmpty()) {
            bits << model.formatLabel;
        }
        if (!model.templateId.isEmpty()) {
            bits << model.templateId;
        }
        if (!model.publishStatus.isEmpty()) {
            bits << model.publishStatus;
        }
        entry.subtitle = bits.join(QStringLiteral(" · "));
        if (entry.subtitle.isEmpty()) {
            entry.subtitle = QObject::tr("Exported model");
        }
        entries.append(entry);
    }
    return entries;
}

} // namespace

namespace LocalLibrary
{

QString kindLabel(Kind kind)
{
    switch (kind) {
    case Kind::Plan:
        return QObject::tr("Plan");
    case Kind::Dataset:
        return QObject::tr("Dataset");
    case Kind::Model:
        return QObject::tr("Model");
    }
    return {};
}

Index scan()
{
    Index index;
    index.plans = scanPlans();
    index.datasets = scanDatasets();
    index.models = scanModels();
    return index;
}

} // namespace LocalLibrary

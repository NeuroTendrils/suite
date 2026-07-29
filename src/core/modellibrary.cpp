#include "core/modellibrary.hpp"

#include "core/projectdir.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonDocument>
#include <QJsonObject>
#include <algorithm>

namespace ModelLibrary
{

QVector<Entry> scan()
{
    QVector<Entry> entries;
    const QString root = ProjectDir::instance().modelsDir();
    if (root.isEmpty()) {
        return entries;
    }

    const QDir models(root);
    if (!models.exists()) {
        return entries;
    }

    const QFileInfoList dirs =
        models.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Time);

    for (const QFileInfo &dirInfo : dirs) {
        const QString metaPath = QDir(dirInfo.absoluteFilePath()).filePath(QStringLiteral("model.json"));
        QFile file(metaPath);
        if (!file.open(QIODevice::ReadOnly)) {
            continue;
        }
        const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
        file.close();
        if (!doc.isObject()) {
            continue;
        }
        const QJsonObject obj = doc.object();
        if (obj.value(QStringLiteral("kind")).toString() != QLatin1String("neurostudio_model")) {
            continue;
        }

        Entry entry;
        entry.meta = obj;
        entry.modelDir = dirInfo.absoluteFilePath();
        entry.metadataPath = metaPath;
        entry.id = dirInfo.fileName();
        entry.title = obj.value(QStringLiteral("title")).toString(entry.id);
        entry.format = obj.value(QStringLiteral("format")).toString();
        entry.formatLabel = obj.value(QStringLiteral("format_label")).toString(entry.format);
        entry.templateId = obj.value(QStringLiteral("template_id")).toString();
        entry.exportedAt = obj.value(QStringLiteral("exported_at")).toString();
        entry.publishStatus =
            obj.value(QStringLiteral("publish_status")).toString(QStringLiteral("unpublished"));

        const QString artifactRel = obj.value(QStringLiteral("artifact")).toString();
        if (!artifactRel.isEmpty()) {
            entry.artifactPath = QDir(entry.modelDir).filePath(artifactRel);
        } else {
            entry.artifactPath = obj.value(QStringLiteral("artifact_path")).toString();
        }

        if (!ProjectDir::instance().contains(entry.modelDir)) {
            continue;
        }
        entries.append(entry);
    }

    std::sort(entries.begin(), entries.end(), [](const Entry &a, const Entry &b) {
        return a.exportedAt > b.exportedAt;
    });
    return entries;
}

} // namespace ModelLibrary

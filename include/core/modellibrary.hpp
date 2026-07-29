#pragma once

#include <QJsonObject>
#include <QString>
#include <QVector>

// Scans project models/ for NeuroStudio export sidecars (model.json).
namespace ModelLibrary
{

struct Entry
{
    QString id;
    QString title;
    QString format;
    QString formatLabel;
    QString templateId;
    QString modelDir;
    QString artifactPath;
    QString metadataPath;
    QString exportedAt;
    QString publishStatus;
    QJsonObject meta;
};

// Returns exported models newest-first. Missing/invalid sidecars are skipped.
[[nodiscard]] QVector<Entry> scan();

} // namespace ModelLibrary

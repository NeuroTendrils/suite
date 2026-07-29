#pragma once

#include <QJsonObject>
#include <QString>
#include <QVector>

// Scans project plans/, datasets/, and models/ for the Hub local library.
namespace LocalLibrary
{

enum class Kind {
    Plan,
    Dataset,
    Model,
};

struct Entry
{
    Kind kind = Kind::Dataset;
    QString id;
    QString title;
    QString path;
    QString subtitle;
    QString modified;
    qint64 sizeBytes = 0;
    QJsonObject meta;
};

struct Index
{
    QVector<Entry> plans;
    QVector<Entry> datasets;
    QVector<Entry> models;

    [[nodiscard]] int total() const
    {
        return plans.size() + datasets.size() + models.size();
    }
};

// Newest / most recently modified first within each bucket.
[[nodiscard]] Index scan();

[[nodiscard]] QString kindLabel(Kind kind);

} // namespace LocalLibrary

#pragma once

#include <QJsonObject>
#include <QString>
#include <QVector>

// Heuristic template ranking for NeuroStudio (no live AI).
// Uses dataset path/kind plus optional fingerprint / run.json hints.
namespace TemplateRecommender
{

struct Suggestion
{
    QString templateId;
    QString title;
    int score = 0;
    QString rationale;
};

struct Result
{
    QVector<Suggestion> ranked; // best first
    QString summary;            // short UI blurb
};

// *fingerprint* may be empty. *datasetPath* should be the selected file.
// *datasetKind* matches StudioDataset kinds (run_output, dataset, …).
[[nodiscard]] Result recommend(const QString &datasetPath,
                               const QString &datasetKind,
                               const QJsonObject &fingerprint = {});

} // namespace TemplateRecommender

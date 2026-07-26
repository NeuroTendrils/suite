#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QVector>

// Builds a default ordered preprocessing plan from a recording fingerprint.
// Heuristic / forms-based only (no LLM).
namespace PlanGenerator
{

struct Step
{
    QString stepId;
    QString title;
    QJsonObject params;
    QString rationale; // short why-this-step note for UI / debugging
};

struct Plan
{
    QVector<Step> steps;
};

[[nodiscard]] Plan fromFingerprint(const QJsonObject &fingerprint);

[[nodiscard]] QJsonObject toJson(const Plan &plan);
[[nodiscard]] Plan fromJson(const QJsonObject &json);

[[nodiscard]] bool isEmpty(const Plan &plan);

} // namespace PlanGenerator

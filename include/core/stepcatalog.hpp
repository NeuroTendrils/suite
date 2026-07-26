#pragma once

#include <QJsonObject>
#include <QJsonValue>
#include <QString>
#include <QStringList>
#include <QVector>

#include <optional>

// Suite-side mirror of NeuroFlow's step catalog (workers/neuroflow/neuroflow/steps.py).
// Keep this list small and in sync; expand later with the worker catalog.
namespace StepCatalog
{

enum class ParamType {
    Number,
    Integer,
    Boolean,
    Enum,
    String,
};

struct ParamSchema
{
    QString id;
    QString label;
    ParamType type = ParamType::Number;
    QJsonValue defaultValue;
    bool required = true;
    std::optional<double> minimum;
    std::optional<double> maximum;
    QStringList enumValues;
    QString unit;
    QString help;
};

struct StepDefinition
{
    QString id;
    QString title;
    QString category;
    QString description;
    QVector<ParamSchema> params;
};

[[nodiscard]] QVector<StepDefinition> all();
[[nodiscard]] QStringList ids();
[[nodiscard]] const StepDefinition *find(const QString &id);

[[nodiscard]] QJsonObject defaultParams(const QString &stepId);

// Returns an empty string when params are valid; otherwise a short error.
[[nodiscard]] QString validateParams(const QString &stepId, const QJsonObject &params);

} // namespace StepCatalog

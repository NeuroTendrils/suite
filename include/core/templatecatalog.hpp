#pragma once

#include <QJsonObject>
#include <QJsonValue>
#include <QString>
#include <QStringList>
#include <QVector>

#include <optional>

// Suite-side mirror of NeuroStudio templates
// (workers/neurostudio/neurostudio/templates.py).
namespace TemplateCatalog
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

struct TemplateDefinition
{
    QString id;
    QString title;
    QString task;         // motor_imagery, erp, …
    QString modelFamily;  // eegnet, shallow, …
    QString backend;      // braindecode
    QString description;
    double inputSfreqHz = 250.0;
    QString inputNotes;
    QVector<ParamSchema> hyperparams;
    QVector<ParamSchema> train;
    QString primaryMetric;
    QStringList reportMetrics;
};

[[nodiscard]] QVector<TemplateDefinition> all();
[[nodiscard]] QStringList ids();
[[nodiscard]] const TemplateDefinition *find(const QString &id);

// Merged hyperparams + train defaults.
[[nodiscard]] QJsonObject defaultConfig(const QString &templateId);

// Returns an empty string when config is valid; otherwise a short error.
[[nodiscard]] QString validateConfig(const QString &templateId, const QJsonObject &config);

} // namespace TemplateCatalog

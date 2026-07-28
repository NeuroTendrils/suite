#include "core/templatecatalog.hpp"

#include <QtGlobal>

namespace TemplateCatalog
{
namespace
{

ParamSchema numberParam(const QString &id,
                        const QString &label,
                        double defaultValue,
                        std::optional<double> minimum = std::nullopt,
                        std::optional<double> maximum = std::nullopt,
                        const QString &unit = {},
                        const QString &help = {},
                        bool required = true)
{
    ParamSchema param;
    param.id = id;
    param.label = label;
    param.type = ParamType::Number;
    param.defaultValue = defaultValue;
    param.minimum = minimum;
    param.maximum = maximum;
    param.unit = unit;
    param.help = help;
    param.required = required;
    return param;
}

ParamSchema intParam(const QString &id,
                     const QString &label,
                     int defaultValue,
                     std::optional<double> minimum = std::nullopt,
                     std::optional<double> maximum = std::nullopt,
                     const QString &help = {})
{
    ParamSchema param = numberParam(id, label, defaultValue, minimum, maximum, {}, help);
    param.type = ParamType::Integer;
    param.defaultValue = defaultValue;
    return param;
}

ParamSchema enumParam(const QString &id,
                      const QString &label,
                      const QStringList &values,
                      const QString &defaultValue,
                      const QString &help = {})
{
    ParamSchema param;
    param.id = id;
    param.label = label;
    param.type = ParamType::Enum;
    param.enumValues = values;
    param.defaultValue = defaultValue;
    param.help = help;
    return param;
}

QVector<ParamSchema> commonTrain(int epochs, int batchSize, double lr)
{
    return {
        intParam(QStringLiteral("epochs"), QStringLiteral("Epochs"), epochs, 1, 500),
        intParam(QStringLiteral("batch_size"), QStringLiteral("Batch size"), batchSize, 1, 512),
        numberParam(QStringLiteral("lr"), QStringLiteral("Learning rate"), lr, 1e-6, 1.0),
        numberParam(QStringLiteral("weight_decay"), QStringLiteral("Weight decay"), 0.0, 0.0, 1.0),
        enumParam(QStringLiteral("optimizer"),
                  QStringLiteral("Optimizer"),
                  {QStringLiteral("adam"), QStringLiteral("adamw"), QStringLiteral("sgd")},
                  QStringLiteral("adam")),
        intParam(QStringLiteral("seed"), QStringLiteral("Seed"), 42, 0, 2147483647),
    };
}

const QVector<TemplateDefinition> &definitions()
{
    // Keep in sync with workers/neurostudio/neurostudio/templates.py.
    static const QVector<TemplateDefinition> kTemplates = [] {
        QVector<TemplateDefinition> out;

        {
            TemplateDefinition t;
            t.id = QStringLiteral("eegnet_mi_v1");
            t.title = QStringLiteral("EEGNet (motor imagery)");
            t.task = QStringLiteral("motor_imagery");
            t.modelFamily = QStringLiteral("eegnet");
            t.backend = QStringLiteral("braindecode");
            t.description = QStringLiteral(
                "Compact EEGNet recipe for motor-imagery decoding. "
                "Wraps braindecode.models.EEGNet with MI-oriented defaults.");
            t.inputSfreqHz = 250.0;
            t.inputNotes = QStringLiteral(
                "Prefer Flow-cleaned continuous or epoched FIF at ~250 Hz.");
            t.hyperparams = {
                intParam(QStringLiteral("F1"), QStringLiteral("Temporal filters (F1)"), 8, 1, 64),
                intParam(QStringLiteral("D"), QStringLiteral("Depth multiplier (D)"), 2, 1, 8),
                intParam(QStringLiteral("kernel_length"),
                         QStringLiteral("Temporal kernel"),
                         64,
                         8,
                         256),
                numberParam(QStringLiteral("drop_prob"),
                            QStringLiteral("Dropout"),
                            0.25,
                            0.0,
                            0.9,
                            {},
                            QStringLiteral("Dropout probability in EEGNet blocks.")),
            };
            t.train = commonTrain(40, 64, 0.001);
            t.primaryMetric = QStringLiteral("accuracy");
            t.reportMetrics = {QStringLiteral("accuracy"),
                               QStringLiteral("balanced_accuracy"),
                               QStringLiteral("confusion")};
            out.append(t);
        }

        {
            TemplateDefinition t;
            t.id = QStringLiteral("shallow_mi_v1");
            t.title = QStringLiteral("ShallowConvNet (motor imagery)");
            t.task = QStringLiteral("motor_imagery");
            t.modelFamily = QStringLiteral("shallow");
            t.backend = QStringLiteral("braindecode");
            t.description = QStringLiteral(
                "Schirrmeister ShallowConvNet-style template for MI. "
                "Good baseline beside EEGNet.");
            t.inputSfreqHz = 250.0;
            t.inputNotes = QStringLiteral(
                "Prefer Flow-cleaned data; bandpass in Flow often 4–38 Hz for MI.");
            t.hyperparams = {
                intParam(QStringLiteral("n_filters_time"),
                         QStringLiteral("Temporal filters"),
                         40,
                         4,
                         128),
                intParam(QStringLiteral("filter_time_length"),
                         QStringLiteral("Temporal kernel"),
                         25,
                         5,
                         128),
                intParam(QStringLiteral("n_filters_spat"),
                         QStringLiteral("Spatial filters"),
                         40,
                         4,
                         128),
                numberParam(QStringLiteral("drop_prob"),
                            QStringLiteral("Dropout"),
                            0.5,
                            0.0,
                            0.9),
            };
            t.train = commonTrain(40, 64, 0.000625);
            t.primaryMetric = QStringLiteral("accuracy");
            t.reportMetrics = {QStringLiteral("accuracy"),
                               QStringLiteral("balanced_accuracy"),
                               QStringLiteral("confusion")};
            out.append(t);
        }

        {
            TemplateDefinition t;
            t.id = QStringLiteral("eegnet_erp_v1");
            t.title = QStringLiteral("EEGNet (ERP)");
            t.task = QStringLiteral("erp");
            t.modelFamily = QStringLiteral("eegnet");
            t.backend = QStringLiteral("braindecode");
            t.description = QStringLiteral(
                "EEGNet recipe tuned for event-related potential / P300-style tasks.");
            t.inputSfreqHz = 250.0;
            t.inputNotes = QStringLiteral(
                "Works best with epoched data around stimulus onsets.");
            t.hyperparams = {
                intParam(QStringLiteral("F1"), QStringLiteral("Temporal filters (F1)"), 8, 1, 64),
                intParam(QStringLiteral("D"), QStringLiteral("Depth multiplier (D)"), 2, 1, 8),
                intParam(QStringLiteral("kernel_length"),
                         QStringLiteral("Temporal kernel"),
                         32,
                         8,
                         256),
                numberParam(QStringLiteral("drop_prob"),
                            QStringLiteral("Dropout"),
                            0.25,
                            0.0,
                            0.9),
            };
            t.train = commonTrain(60, 32, 0.001);
            t.primaryMetric = QStringLiteral("balanced_accuracy");
            t.reportMetrics = {QStringLiteral("accuracy"),
                               QStringLiteral("balanced_accuracy"),
                               QStringLiteral("auc"),
                               QStringLiteral("confusion")};
            out.append(t);
        }

        return out;
    }();
    return kTemplates;
}

bool isNumberLike(const QJsonValue &value)
{
    return value.isDouble() || value.isString();
}

double asNumber(const QJsonValue &value, bool *ok)
{
    if (value.isDouble()) {
        *ok = true;
        return value.toDouble();
    }
    if (value.isString()) {
        bool localOk = false;
        const double number = value.toString().toDouble(&localOk);
        *ok = localOk;
        return number;
    }
    *ok = false;
    return 0.0;
}

QString validateParamList(const QString &templateId,
                          const QVector<ParamSchema> &schemas,
                          const QJsonObject &config)
{
    for (const ParamSchema &schema : schemas) {
        if (!config.contains(schema.id)) {
            if (schema.required) {
                return QStringLiteral("Missing parameter “%1” on template “%2”.")
                    .arg(schema.id, templateId);
            }
            continue;
        }

        const QJsonValue value = config.value(schema.id);
        switch (schema.type) {
        case ParamType::Boolean:
            if (!value.isBool()) {
                return QStringLiteral("Parameter “%1” must be a boolean.").arg(schema.id);
            }
            break;
        case ParamType::Enum:
            if (!value.isString() || !schema.enumValues.contains(value.toString())) {
                return QStringLiteral("Parameter “%1” must be one of: %2.")
                    .arg(schema.id, schema.enumValues.join(QStringLiteral(", ")));
            }
            break;
        case ParamType::String:
            if (!value.isString()) {
                return QStringLiteral("Parameter “%1” must be a string.").arg(schema.id);
            }
            break;
        case ParamType::Integer:
        case ParamType::Number: {
            if (!isNumberLike(value)) {
                return QStringLiteral("Parameter “%1” must be a number.").arg(schema.id);
            }
            bool ok = false;
            const double number = asNumber(value, &ok);
            if (!ok) {
                return QStringLiteral("Parameter “%1” is not a valid number.").arg(schema.id);
            }
            if (schema.type == ParamType::Integer && qAbs(number - qRound(number)) > 1e-9) {
                return QStringLiteral("Parameter “%1” must be an integer.").arg(schema.id);
            }
            if (schema.minimum.has_value() && number < *schema.minimum) {
                return QStringLiteral("Parameter “%1” must be ≥ %2.")
                    .arg(schema.id)
                    .arg(*schema.minimum);
            }
            if (schema.maximum.has_value() && number > *schema.maximum) {
                return QStringLiteral("Parameter “%1” must be ≤ %2.")
                    .arg(schema.id)
                    .arg(*schema.maximum);
            }
            break;
        }
        }
    }
    return {};
}

} // namespace

QVector<TemplateDefinition> all()
{
    return definitions();
}

QStringList ids()
{
    QStringList out;
    for (const TemplateDefinition &item : definitions()) {
        out << item.id;
    }
    return out;
}

const TemplateDefinition *find(const QString &id)
{
    for (const TemplateDefinition &item : definitions()) {
        if (item.id == id) {
            return &item;
        }
    }
    return nullptr;
}

QJsonObject defaultConfig(const QString &templateId)
{
    const TemplateDefinition *item = find(templateId);
    if (item == nullptr) {
        return {};
    }

    QJsonObject config;
    for (const ParamSchema &param : item->hyperparams) {
        config.insert(param.id, param.defaultValue);
    }
    for (const ParamSchema &param : item->train) {
        config.insert(param.id, param.defaultValue);
    }
    return config;
}

QString validateConfig(const QString &templateId, const QJsonObject &config)
{
    const TemplateDefinition *item = find(templateId);
    if (item == nullptr) {
        return QStringLiteral("Unknown template: %1").arg(templateId);
    }

    QString error = validateParamList(templateId, item->hyperparams, config);
    if (!error.isEmpty()) {
        return error;
    }
    return validateParamList(templateId, item->train, config);
}

} // namespace TemplateCatalog

#include "core/stepcatalog.hpp"

#include <QtGlobal>

namespace StepCatalog
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

ParamSchema boolParam(const QString &id,
                      const QString &label,
                      bool defaultValue,
                      const QString &help = {})
{
    ParamSchema param;
    param.id = id;
    param.label = label;
    param.type = ParamType::Boolean;
    param.defaultValue = defaultValue;
    param.help = help;
    return param;
}

ParamSchema stringParam(const QString &id,
                        const QString &label,
                        const QString &defaultValue = {},
                        bool required = false,
                        const QString &help = {})
{
    ParamSchema param;
    param.id = id;
    param.label = label;
    param.type = ParamType::String;
    param.defaultValue = defaultValue;
    param.required = required;
    param.help = help;
    return param;
}

const QVector<StepDefinition> &definitions()
{
    // Keep in sync with workers/neuroflow/neuroflow/steps.py (minimal set).
    static const QVector<StepDefinition> steps = {
        {
            QStringLiteral("filter"),
            QStringLiteral("Filter"),
            QStringLiteral("filtering"),
            QStringLiteral("Frequency filter (high-pass, low-pass, or band-pass)."),
            {
                numberParam(QStringLiteral("l_freq"), QStringLiteral("Low cutoff"), 1.0, 0.0,
                            500.0, QStringLiteral("Hz"),
                            QStringLiteral("High-pass edge; 0 disables high-pass.")),
                numberParam(QStringLiteral("h_freq"), QStringLiteral("High cutoff"), 40.0, 0.0,
                            2000.0, QStringLiteral("Hz"),
                            QStringLiteral("Low-pass edge; 0 disables low-pass.")),
                enumParam(QStringLiteral("method"), QStringLiteral("Method"),
                          {QStringLiteral("fir"), QStringLiteral("iir")},
                          QStringLiteral("fir"),
                          QStringLiteral("FIR is the usual choice for EEG.")),
            },
        },
        {
            QStringLiteral("notch"),
            QStringLiteral("Notch filter"),
            QStringLiteral("filtering"),
            QStringLiteral("Remove power-line noise (and optional harmonics)."),
            {
                enumParam(QStringLiteral("freq"), QStringLiteral("Line frequency"),
                          {QStringLiteral("50"), QStringLiteral("60")},
                          QStringLiteral("60"), QStringLiteral("Mains frequency in Hz.")),
                boolParam(QStringLiteral("harmonics"), QStringLiteral("Include harmonics"), true,
                          QStringLiteral("Also notch 2× and 3× the line frequency.")),
            },
        },
        {
            QStringLiteral("reref"),
            QStringLiteral("Re-reference"),
            QStringLiteral("channels"),
            QStringLiteral("Change the EEG reference."),
            {
                enumParam(QStringLiteral("reference"), QStringLiteral("Reference"),
                          {QStringLiteral("average"), QStringLiteral("channel")},
                          QStringLiteral("average")),
                stringParam(QStringLiteral("channel"), QStringLiteral("Channel"), {}, false,
                            QStringLiteral("Required when reference is channel (e.g. Cz).")),
            },
        },
        {
            QStringLiteral("resample"),
            QStringLiteral("Resample"),
            QStringLiteral("time"),
            QStringLiteral("Change the sampling rate."),
            {
                numberParam(QStringLiteral("sfreq"), QStringLiteral("New sampling rate"), 250.0,
                            1.0, 5000.0, QStringLiteral("Hz")),
            },
        },
        {
            QStringLiteral("ica"),
            QStringLiteral("ICA"),
            QStringLiteral("artifacts"),
            QStringLiteral("Fit ICA and exclude obvious artifact components (EOG heuristics)."),
            {
                numberParam(QStringLiteral("n_components"), QStringLiteral("Components"), 0.99, 0.0,
                            512.0, {},
                            QStringLiteral(
                                "Float in (0,1] = variance fraction; integer ≥1 = component count.")),
                boolParam(QStringLiteral("find_bads_eog"), QStringLiteral("Auto-exclude EOG-like"),
                          true),
                stringParam(QStringLiteral("exclude"), QStringLiteral("Exclude indices"), {}, false,
                            QStringLiteral("Optional comma-separated ICA component indices to drop.")),
            },
        },
        {
            QStringLiteral("epoch"),
            QStringLiteral("Epoch"),
            QStringLiteral("epochs"),
            QStringLiteral("Cut continuous data into fixed-length segments."),
            {
                numberParam(QStringLiteral("duration"), QStringLiteral("Epoch length"), 2.0, 0.05,
                            3600.0, QStringLiteral("s")),
                numberParam(QStringLiteral("overlap"), QStringLiteral("Overlap"), 0.0, 0.0, 3599.0,
                            QStringLiteral("s"),
                            QStringLiteral("Must be smaller than epoch length.")),
            },
        },
    };
    return steps;
}

QString typeName(ParamType type)
{
    switch (type) {
    case ParamType::Number:
        return QStringLiteral("number");
    case ParamType::Integer:
        return QStringLiteral("integer");
    case ParamType::Boolean:
        return QStringLiteral("boolean");
    case ParamType::Enum:
        return QStringLiteral("enum");
    case ParamType::String:
        return QStringLiteral("string");
    }
    return QStringLiteral("unknown");
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

} // namespace

QVector<StepDefinition> all()
{
    return definitions();
}

QStringList ids()
{
    QStringList out;
    for (const StepDefinition &step : definitions()) {
        out << step.id;
    }
    return out;
}

const StepDefinition *find(const QString &id)
{
    for (const StepDefinition &step : definitions()) {
        if (step.id == id) {
            return &step;
        }
    }
    return nullptr;
}

QJsonObject defaultParams(const QString &stepId)
{
    const StepDefinition *step = find(stepId);
    if (step == nullptr) {
        return {};
    }

    QJsonObject params;
    for (const ParamSchema &param : step->params) {
        params.insert(param.id, param.defaultValue);
    }
    return params;
}

QString validateParams(const QString &stepId, const QJsonObject &params)
{
    const StepDefinition *step = find(stepId);
    if (step == nullptr) {
        return QStringLiteral("Unknown step: %1").arg(stepId);
    }

    for (const ParamSchema &schema : step->params) {
        if (!params.contains(schema.id)) {
            if (schema.required) {
                return QStringLiteral("Missing parameter “%1” on step “%2”.")
                    .arg(schema.id, stepId);
            }
            continue;
        }

        const QJsonValue value = params.value(schema.id);

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
            if (schema.required && value.toString().trimmed().isEmpty()) {
                return QStringLiteral("Parameter “%1” must not be empty.").arg(schema.id);
            }
            break;

        case ParamType::Integer:
        case ParamType::Number: {
            if (!isNumberLike(value)) {
                return QStringLiteral("Parameter “%1” must be a %2.")
                    .arg(schema.id, typeName(schema.type));
            }
            bool ok = false;
            const double number = asNumber(value, &ok);
            if (!ok || number != number) {
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

    if (stepId == QLatin1String("filter")) {
        bool okLow = false;
        bool okHigh = false;
        const double low = asNumber(params.value(QStringLiteral("l_freq")), &okLow);
        const double high = asNumber(params.value(QStringLiteral("h_freq")), &okHigh);
        if (okLow && okHigh && low > 0.0 && high > 0.0 && low >= high) {
            return QStringLiteral("filter: l_freq must be less than h_freq when both are set.");
        }
    }

    if (stepId == QLatin1String("reref")) {
        const QString reference = params.value(QStringLiteral("reference")).toString();
        if (reference == QLatin1String("channel")
            && params.value(QStringLiteral("channel")).toString().trimmed().isEmpty()) {
            return QStringLiteral("reref: channel is required when reference is “channel”.");
        }
    }

    if (stepId == QLatin1String("epoch")) {
        bool okDuration = false;
        bool okOverlap = false;
        const double duration = asNumber(params.value(QStringLiteral("duration")), &okDuration);
        const double overlap = asNumber(params.value(QStringLiteral("overlap")), &okOverlap);
        if (okDuration && okOverlap && overlap >= duration) {
            return QStringLiteral("epoch: overlap must be smaller than duration.");
        }
    }

    return {};
}

} // namespace StepCatalog

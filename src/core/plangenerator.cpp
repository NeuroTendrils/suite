#include "core/plangenerator.hpp"

#include "core/stepcatalog.hpp"

#include <QJsonArray>
#include <QtGlobal>

namespace PlanGenerator
{
namespace
{

constexpr double kTargetSfreq = 250.0;
constexpr double kResampleIfAbove = 256.0;
constexpr int kMinChannelsForIca = 8;
constexpr double kMinDurationForIcaSec = 30.0;

Step makeStep(const QString &stepId, const QJsonObject &params, const QString &rationale)
{
    Step step;
    step.stepId = stepId;
    step.params = params;
    step.rationale = rationale;

    if (const StepCatalog::StepDefinition *def = StepCatalog::find(stepId)) {
        step.title = def->title;
    } else {
        step.title = stepId;
    }
    return step;
}

Step makeDefaultStep(const QString &stepId, const QString &rationale)
{
    return makeStep(stepId, StepCatalog::defaultParams(stepId), rationale);
}

int countEegLikeChannels(const QJsonObject &fingerprint)
{
    const QJsonArray types = fingerprint.value(QStringLiteral("ch_types")).toArray();
    if (types.isEmpty()) {
        return fingerprint.value(QStringLiteral("n_channels")).toInt();
    }

    int count = 0;
    for (const QJsonValue &value : types) {
        const QString type = value.toString().toLower();
        if (type == QLatin1String("eeg") || type == QLatin1String("eog")) {
            ++count;
        }
    }
    return count > 0 ? count : fingerprint.value(QStringLiteral("n_channels")).toInt();
}

QString guessLineFreq(const QJsonObject &fingerprint)
{
    // Fingerprint does not encode country. Prefer 60 unless channel names hint otherwise.
    Q_UNUSED(fingerprint);
    return QStringLiteral("60");
}

} // namespace

Plan fromFingerprint(const QJsonObject &fingerprint)
{
    Plan plan;
    if (fingerprint.isEmpty()) {
        return plan;
    }

    const double sfreq = fingerprint.value(QStringLiteral("sfreq")).toDouble();
    const double duration = fingerprint.value(QStringLiteral("duration_sec")).toDouble();
    const int nChannels = fingerprint.value(QStringLiteral("n_channels")).toInt();
    const int eegLike = countEegLikeChannels(fingerprint);

    // 1) Band-pass / high-pass style filter (catalog defaults: 1–40 Hz, FIR).
    {
        QJsonObject params = StepCatalog::defaultParams(QStringLiteral("filter"));
        if (sfreq > 0.0) {
            const double nyquist = sfreq / 2.0;
            const double hFreq = params.value(QStringLiteral("h_freq")).toDouble();
            if (hFreq >= nyquist) {
                params.insert(QStringLiteral("h_freq"), qMax(1.0, nyquist * 0.9));
            }
        }
        plan.steps.append(makeStep(
            QStringLiteral("filter"),
            params,
            QStringLiteral("Remove slow drift and high-frequency noise before later steps.")));
    }

    // 2) Notch for mains.
    {
        QJsonObject params = StepCatalog::defaultParams(QStringLiteral("notch"));
        params.insert(QStringLiteral("freq"), guessLineFreq(fingerprint));
        plan.steps.append(makeStep(
            QStringLiteral("notch"),
            params,
            QStringLiteral("Attenuate power-line interference.")));
    }

    // 3) Re-reference when we have enough EEG-like channels.
    if (eegLike >= 2) {
        plan.steps.append(makeDefaultStep(
            QStringLiteral("reref"),
            QStringLiteral("Average reference for multi-channel EEG.")));
    }

    // 4) Resample only when clearly oversampled for typical BCI/ERP work.
    if (sfreq > kResampleIfAbove) {
        QJsonObject params = StepCatalog::defaultParams(QStringLiteral("resample"));
        params.insert(QStringLiteral("sfreq"), kTargetSfreq);
        plan.steps.append(makeStep(
            QStringLiteral("resample"),
            params,
            QStringLiteral("Downsample to %1 Hz after filtering to speed later steps.")
                .arg(QString::number(kTargetSfreq, 'f', 0))));
    }

    // 5) ICA when the recording is wide/long enough for a stable fit.
    if (nChannels >= kMinChannelsForIca && duration >= kMinDurationForIcaSec) {
        plan.steps.append(makeDefaultStep(
            QStringLiteral("ica"),
            QStringLiteral("Enough channels and duration for an ICA artifact pass.")));
    }

    // 6) Fixed-length epochs as a simple continuous-data default.
    plan.steps.append(makeDefaultStep(
        QStringLiteral("epoch"),
        QStringLiteral("Segment continuous data into fixed-length windows.")));

    return plan;
}

QJsonObject toJson(const Plan &plan)
{
    QJsonArray steps;
    for (const Step &step : plan.steps) {
        steps.append(QJsonObject{
            {QStringLiteral("step_id"), step.stepId},
            {QStringLiteral("title"), step.title},
            {QStringLiteral("params"), step.params},
            {QStringLiteral("rationale"), step.rationale},
        });
    }
    return QJsonObject{
        {QStringLiteral("v"), 1},
        {QStringLiteral("steps"), steps},
    };
}

Plan fromJson(const QJsonObject &json)
{
    Plan plan;
    const QJsonArray steps = json.value(QStringLiteral("steps")).toArray();
    for (const QJsonValue &value : steps) {
        const QJsonObject object = value.toObject();
        Step step;
        step.stepId = object.value(QStringLiteral("step_id")).toString();
        step.title = object.value(QStringLiteral("title")).toString();
        step.params = object.value(QStringLiteral("params")).toObject();
        step.rationale = object.value(QStringLiteral("rationale")).toString();
        if (step.title.isEmpty()) {
            if (const StepCatalog::StepDefinition *def = StepCatalog::find(step.stepId)) {
                step.title = def->title;
            } else {
                step.title = step.stepId;
            }
        }
        if (!step.stepId.isEmpty()) {
            plan.steps.append(step);
        }
    }
    return plan;
}

bool isEmpty(const Plan &plan)
{
    return plan.steps.isEmpty();
}

} // namespace PlanGenerator

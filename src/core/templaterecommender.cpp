#include "core/templaterecommender.hpp"

#include "core/templatecatalog.hpp"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>

#include <algorithm>

namespace TemplateRecommender
{
namespace
{

QString lowerPath(const QString &path)
{
    return path.toLower();
}

QJsonObject tryLoadRunSidecar(const QString &datasetPath)
{
    const QFileInfo info(datasetPath);
    const QString sidecar = info.dir().filePath(QStringLiteral("run.json"));
    QFile file(sidecar);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        return {};
    }
    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &error);
    if (error.error != QJsonParseError::NoError || !doc.isObject()) {
        return {};
    }
    return doc.object();
}

bool pathHintsErp(const QString &pathLower)
{
    return pathLower.contains(QLatin1String("erp"))
           || pathLower.contains(QLatin1String("p300"))
           || pathLower.contains(QLatin1String("oddball"))
           || pathLower.contains(QLatin1String("n400"));
}

bool pathHintsMi(const QString &pathLower)
{
    return pathLower.contains(QLatin1String("mi"))
           || pathLower.contains(QLatin1String("motor"))
           || pathLower.contains(QLatin1String("imagery"))
           || pathLower.contains(QLatin1String("bci"));
}

bool planLooksEpoched(const QJsonObject &runDoc)
{
    const QJsonObject plan = runDoc.value(QStringLiteral("plan")).toObject();
    const QJsonArray steps = plan.value(QStringLiteral("steps")).toArray();
    for (const QJsonValue &value : steps) {
        if (value.toObject().value(QStringLiteral("step_id")).toString()
            == QLatin1String("epoch")) {
            return true;
        }
    }
    const QJsonObject result = runDoc.value(QStringLiteral("result")).toObject();
    return result.value(QStringLiteral("output_kind")).toString() == QLatin1String("epochs");
}

int baseScoreForTask(const QString &task, bool wantErp, bool wantMi)
{
    if (wantErp && task == QLatin1String("erp")) {
        return 100;
    }
    if (wantMi && task == QLatin1String("motor_imagery")) {
        return 100;
    }
    if (!wantErp && !wantMi && task == QLatin1String("motor_imagery")) {
        return 70; // default BCI path
    }
    if (!wantErp && !wantMi && task == QLatin1String("erp")) {
        return 40;
    }
    if (wantErp && task == QLatin1String("motor_imagery")) {
        return 35;
    }
    if (wantMi && task == QLatin1String("erp")) {
        return 35;
    }
    return 20;
}

} // namespace

Result recommend(const QString &datasetPath,
                 const QString &datasetKind,
                 const QJsonObject &fingerprint)
{
    Result result;
    const QString pathLower = lowerPath(datasetPath);
    const QJsonObject runDoc = tryLoadRunSidecar(datasetPath);

    bool wantErp = pathHintsErp(pathLower);
    bool wantMi = pathHintsMi(pathLower);

    // Fingerprint / run metadata can refine later; for now use epoch hint weakly.
    Q_UNUSED(fingerprint);
    const bool epoched = planLooksEpoched(runDoc);
    if (!wantErp && !wantMi && epoched) {
        // Fixed-length epochs from Flow are still often MI windows; keep MI ahead of ERP.
        wantMi = true;
    }

    QStringList reasons;
    if (wantErp) {
        reasons << QStringLiteral("path suggests ERP/P300");
    }
    if (wantMi) {
        reasons << QStringLiteral("path or run suggests motor imagery / BCI");
    }
    if (datasetKind == QLatin1String("run_output")) {
        reasons << QStringLiteral("NeuroFlow run output");
    }
    if (epoched) {
        reasons << QStringLiteral("run produced epochs");
    }
    if (reasons.isEmpty()) {
        reasons << QStringLiteral("default MI-first ranking");
    }

    for (const TemplateCatalog::TemplateDefinition &item : TemplateCatalog::all()) {
        Suggestion suggestion;
        suggestion.templateId = item.id;
        suggestion.title = item.title;
        suggestion.score = baseScoreForTask(item.task, wantErp, wantMi);

        // Prefer EEGNet slightly as the compact default within a task.
        if (item.modelFamily == QLatin1String("eegnet")) {
            suggestion.score += 5;
        }
        if (item.modelFamily == QLatin1String("shallow") && wantMi) {
            suggestion.score += 2; // solid MI baseline
        }

        if (item.task == QLatin1String("erp") && wantErp) {
            suggestion.rationale = QStringLiteral("Matches ERP-oriented naming/hints.");
        } else if (item.task == QLatin1String("motor_imagery") && wantMi) {
            suggestion.rationale = QStringLiteral("Matches motor-imagery / BCI hints.");
        } else if (item.task == QLatin1String("motor_imagery")) {
            suggestion.rationale = QStringLiteral("Default MI starter template.");
        } else {
            suggestion.rationale = QStringLiteral("Alternate task recipe.");
        }

        result.ranked.append(suggestion);
    }

    std::sort(result.ranked.begin(),
              result.ranked.end(),
              [](const Suggestion &a, const Suggestion &b) {
                  if (a.score != b.score) {
                      return a.score > b.score;
                  }
                  return a.templateId < b.templateId;
              });

    if (!result.ranked.isEmpty()) {
        result.summary = QStringLiteral("Suggested: %1 (%2).")
                             .arg(result.ranked.first().title, reasons.join(QStringLiteral("; ")));
    } else {
        result.summary = QStringLiteral("No templates available.");
    }
    return result;
}

} // namespace TemplateRecommender

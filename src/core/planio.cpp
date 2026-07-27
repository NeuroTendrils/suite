#include "core/planio.hpp"

#include "core/projectdir.hpp"
#include "core/reprometa.hpp"
#include "core/stepcatalog.hpp"

#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIODevice>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>

namespace
{

QString resolvePath(const QString &path)
{
    const QString cleaned = QDir::cleanPath(QFileInfo(path).absoluteFilePath());
    const QFileInfo info(cleaned);
    const QString canonical = info.canonicalFilePath();
    return canonical.isEmpty() ? cleaned : canonical;
}

bool isUnderPlansDir(const QString &path)
{
    const QString plans = ProjectDir::instance().plansDir();
    if (plans.isEmpty() || path.isEmpty()) {
        return false;
    }

    const QString resolved = resolvePath(path);
    const QString resolvedPlans = resolvePath(plans);

#ifdef Q_OS_WIN
    constexpr Qt::CaseSensitivity caseSensitivity = Qt::CaseInsensitive;
#else
    constexpr Qt::CaseSensitivity caseSensitivity = Qt::CaseSensitive;
#endif

    return resolved.compare(resolvedPlans, caseSensitivity) == 0
           || resolved.startsWith(resolvedPlans + QLatin1Char('/'), caseSensitivity);
}

QString uniqueDestination(const QDir &plans, const QString &fileName)
{
    const QFileInfo info(fileName);
    const QString base = info.completeBaseName();
    const QString suffix = info.suffix().isEmpty()
                               ? QStringLiteral(".json")
                               : QStringLiteral(".") + info.suffix();

    QString candidate = fileName.endsWith(QLatin1String(".json"), Qt::CaseInsensitive)
                            ? fileName
                            : base + suffix;
    int attempt = 1;
    while (plans.exists(candidate)) {
        candidate = QStringLiteral("%1_%2%3").arg(base).arg(attempt).arg(suffix);
        ++attempt;
    }
    return plans.filePath(candidate);
}

} // namespace

namespace PlanIo
{

QStringList fileFilters()
{
    return {
        QStringLiteral("NeuroFlow plans (*.json)"),
        QStringLiteral("All files (*)"),
    };
}

QString validateDocument(const QJsonObject &document)
{
    if (document.isEmpty()) {
        return QStringLiteral("Plan document is empty.");
    }

    const QJsonValue versionValue = document.value(QStringLiteral("v"));
    if (!versionValue.isUndefined() && !versionValue.isNull()) {
        if (!versionValue.isDouble() || versionValue.toInt() != 1) {
            return QStringLiteral("Unsupported plan schema version.");
        }
    }

    const QJsonValue stepsValue = document.value(QStringLiteral("steps"));
    if (!stepsValue.isArray()) {
        return QStringLiteral("Plan is missing a steps array.");
    }

    const QJsonArray steps = stepsValue.toArray();
    if (steps.isEmpty()) {
        return QStringLiteral("Plan has no steps.");
    }

    for (int i = 0; i < steps.size(); ++i) {
        if (!steps.at(i).isObject()) {
            return QStringLiteral("Step %1 is not an object.").arg(i + 1);
        }

        const QJsonObject step = steps.at(i).toObject();
        const QString stepId = step.value(QStringLiteral("step_id")).toString().trimmed();
        if (stepId.isEmpty()) {
            return QStringLiteral("Step %1 is missing step_id.").arg(i + 1);
        }
        if (!StepCatalog::find(stepId)) {
            return QStringLiteral("Step %1 uses unknown step_id “%2”.")
                .arg(i + 1)
                .arg(stepId);
        }

        const QJsonObject params = step.value(QStringLiteral("params")).toObject();
        const QString paramError = StepCatalog::validateParams(stepId, params);
        if (!paramError.isEmpty()) {
            return QStringLiteral("Step %1 (%2): %3").arg(i + 1).arg(stepId, paramError);
        }
    }

    return {};
}

QJsonObject documentFromPlan(const PlanGenerator::Plan &plan, const QJsonObject &metadata)
{
    QJsonObject document = PlanGenerator::toJson(plan);
    for (auto it = metadata.constBegin(); it != metadata.constEnd(); ++it) {
        if (it.key() == QLatin1String("v") || it.key() == QLatin1String("steps")) {
            continue;
        }
        document.insert(it.key(), it.value());
    }
    if (!document.contains(QStringLiteral("saved_at"))) {
        document.insert(QStringLiteral("saved_at"),
                        QDateTime::currentDateTimeUtc().toString(Qt::ISODate));
    }
    // Always stamp seed / reproducibility policy so re-runs keep the same steps
    // and stochastic params unless the caller overrides reproducibility.
    if (!document.contains(QStringLiteral("reproducibility"))) {
        document.insert(QStringLiteral("reproducibility"), ReproMeta::planStamp());
    }
    return document;
}

Result save(const PlanGenerator::Plan &plan,
            const QString &destinationPath,
            const QJsonObject &metadata)
{
    Result result;
    result.path = destinationPath;

    if (ProjectDir::instance().root().isEmpty()) {
        result.error = QStringLiteral("No project folder configured.");
        return result;
    }
    if (PlanGenerator::isEmpty(plan)) {
        result.error = QStringLiteral("Cannot save an empty plan.");
        return result;
    }
    if (destinationPath.trimmed().isEmpty()) {
        result.error = QStringLiteral("No destination path.");
        return result;
    }
    if (!isUnderPlansDir(destinationPath)) {
        result.error = QStringLiteral("Plans must be saved inside the project plans/ folder.");
        return result;
    }

    const QJsonObject document = documentFromPlan(plan, metadata);
    const QString schemaError = validateDocument(document);
    if (!schemaError.isEmpty()) {
        result.error = schemaError;
        return result;
    }

    QDir().mkpath(QFileInfo(destinationPath).absolutePath());

    QFile file(destinationPath);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
        result.error = QStringLiteral("Could not write plan file.");
        return result;
    }

    const QByteArray bytes = QJsonDocument(document).toJson(QJsonDocument::Indented);
    if (file.write(bytes) != bytes.size()) {
        result.error = QStringLiteral("Failed while writing plan file.");
        return result;
    }

    result.ok = true;
    result.plan = plan;
    result.document = document;
    result.path = QFileInfo(destinationPath).absoluteFilePath();
    return result;
}

Result load(const QString &sourcePath)
{
    Result result;
    result.path = sourcePath;

    if (ProjectDir::instance().root().isEmpty()) {
        result.error = QStringLiteral("No project folder configured.");
        return result;
    }
    if (sourcePath.trimmed().isEmpty()) {
        result.error = QStringLiteral("No plan file selected.");
        return result;
    }
    if (!ProjectDir::instance().contains(sourcePath)) {
        result.error = QStringLiteral("Plan file must be inside the project folder.");
        return result;
    }

    QFile file(sourcePath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        result.error = QStringLiteral("Could not open plan file.");
        return result;
    }

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
        result.error = QStringLiteral("Plan file is not valid JSON.");
        return result;
    }

    const QJsonObject document = doc.object();
    const QString schemaError = validateDocument(document);
    if (!schemaError.isEmpty()) {
        result.error = schemaError;
        return result;
    }

    result.ok = true;
    result.document = document;
    result.plan = PlanGenerator::fromJson(document);
    result.path = QFileInfo(sourcePath).absoluteFilePath();
    return result;
}

QString suggestSavePath(const QString &preferredBaseName)
{
    const QString plansRoot = ProjectDir::instance().plansDir();
    if (plansRoot.isEmpty()) {
        return {};
    }

    QDir plans(plansRoot);
    plans.mkpath(QStringLiteral("."));

    QString base = preferredBaseName.trimmed();
    if (base.isEmpty()) {
        base = QStringLiteral("plan_%1")
                   .arg(QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd_HHmmss")));
    } else {
        QString sanitized;
        sanitized.reserve(base.size());
        for (const QChar ch : base) {
            if (ch.isLetterOrNumber() || ch == QLatin1Char('_') || ch == QLatin1Char('-')) {
                sanitized.append(ch);
            } else {
                sanitized.append(QLatin1Char('_'));
            }
        }
        base = sanitized;
    }

    if (!base.endsWith(QLatin1String(".json"), Qt::CaseInsensitive)) {
        base += QStringLiteral(".json");
    }

    return uniqueDestination(plans, base);
}

} // namespace PlanIo

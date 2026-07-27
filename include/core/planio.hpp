#pragma once

#include "core/plangenerator.hpp"

#include <QJsonObject>
#include <QString>
#include <QStringList>

// Persists NeuroFlow plan JSON under the project plans/ folder.
// Paths are always sandbox-checked against ProjectDir.
namespace PlanIo
{

struct Result
{
    bool ok = false;
    QString path;
    PlanGenerator::Plan plan;
    QJsonObject document;
    QString error;
};

[[nodiscard]] QStringList fileFilters();

// Returns an empty string when the document is a valid v1 plan; otherwise a short error.
[[nodiscard]] QString validateDocument(const QJsonObject &document);

// Builds the on-disk document (schema v1 + optional metadata).
[[nodiscard]] QJsonObject documentFromPlan(const PlanGenerator::Plan &plan,
                                           const QJsonObject &metadata = {});

// Writes plan JSON. destinationPath must resolve inside plans/.
[[nodiscard]] Result save(const PlanGenerator::Plan &plan,
                          const QString &destinationPath,
                          const QJsonObject &metadata = {});

// Reads and validates a plan JSON file inside the project sandbox (preferably plans/).
[[nodiscard]] Result load(const QString &sourcePath);

// Suggests a unique path under plans/ for a new save.
[[nodiscard]] QString suggestSavePath(const QString &preferredBaseName = {});

} // namespace PlanIo

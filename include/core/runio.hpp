#pragma once

#include "core/plangenerator.hpp"

#include <QJsonObject>
#include <QString>

// Allocates run directories under project runs/ and writes metadata sidecars
// that link cleaned outputs back to the plan that produced them.
namespace RunIo
{

struct Paths
{
    QString runDir;
    QString outputPath;
    QString metadataPath;
};

struct Result
{
    bool ok = false;
    QString path;
    QString error;
};

// Suggests a unique run folder + default cleaned .fif path under runs/.
[[nodiscard]] Paths suggestPaths(const QString &preferredBaseName = {});

// Writes run.json linking input, plan, and worker result (must be inside runs/).
[[nodiscard]] Result writeMetadata(const QString &metadataPath,
                                   const QString &inputPath,
                                   const QString &outputPath,
                                   const PlanGenerator::Plan &plan,
                                   const QString &planPath,
                                   const QJsonObject &workerResult);

} // namespace RunIo

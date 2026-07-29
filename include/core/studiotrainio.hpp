#pragma once

#include <QString>

// Allocates NeuroStudio train artifact folders under project runs/.
namespace StudioTrainIo
{

struct Paths
{
    QString runDir;
    QString checkpointPath;
    QString metricsPath;
    QString trainMetaPath;
};

// Suggests a unique runs/<name>_<stamp>/ folder for train artifacts.
[[nodiscard]] Paths suggestPaths(const QString &preferredBaseName = {});

} // namespace StudioTrainIo

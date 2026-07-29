#pragma once

#include <QString>

// Allocates NeuroStudio export folders under project models/.
namespace StudioExportIo
{

struct Paths
{
    QString modelDir;
    QString metadataPath;
};

// Suggests a unique models/<name>_<stamp>/ folder for export artifacts.
[[nodiscard]] Paths suggestPaths(const QString &preferredBaseName = {});

} // namespace StudioExportIo

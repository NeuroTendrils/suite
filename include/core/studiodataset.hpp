#pragma once

#include <QString>
#include <QStringList>

// Selects a sandboxed training dataset for NeuroStudio.
// Prefer NeuroFlow runs/ outputs; also allow datasets/ (and other in-project files).
// Outside-project paths are rejected (no copy in this phase).
namespace StudioDataset
{

struct Result
{
    bool ok = false;
    QString path;        // absolute file path inside the project sandbox
    QString displayName; // short label for UI
    QString kind;        // "run_output" | "dataset" | "project_file"
    QString error;
};

[[nodiscard]] QStringList fileFilters();
[[nodiscard]] QStringList allowedSuffixes();

// Best starting folder for the file dialog (runs/ → datasets/ → project root).
[[nodiscard]] QString preferredStartDir();

// Validates *sourcePath* (file, or a runs/ folder containing cleaned.fif).
// Must resolve inside ProjectDir.
[[nodiscard]] Result selectPath(const QString &sourcePath);

} // namespace StudioDataset

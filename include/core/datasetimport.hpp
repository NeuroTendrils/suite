#pragma once

#include <QString>
#include <QStringList>

// Imports a raw EEG recording into the project datasets/ folder.
// Destination paths are always sandbox-checked against ProjectDir.
namespace DatasetImport
{

struct Result
{
    bool ok = false;
    bool copied = false;
    QString sourcePath;
    QString datasetPath; // absolute path inside datasets/
    QString error;
};

// Common raw EEG extensions accepted by the file picker.
[[nodiscard]] QStringList fileFilters();
[[nodiscard]] QStringList allowedSuffixes();

// If source is already inside the project sandbox, registers it in place
// (no copy). Otherwise copies into datasets/ under a unique name.
[[nodiscard]] Result importRecording(const QString &sourcePath);

} // namespace DatasetImport

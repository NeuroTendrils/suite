#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>

// Log-safe redaction mirroring workers/_shared/nt_ipc/redact.py.
// Never put raw EEG samples into application logs.
namespace IpcRedact
{

[[nodiscard]] QJsonValue redact(const QJsonValue &value, const QString &key = {});
[[nodiscard]] QString redactText(const QString &text);

} // namespace IpcRedact

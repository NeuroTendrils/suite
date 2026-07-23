#include "core/ipcredact.hpp"

#include <QJsonDocument>
#include <QRegularExpression>
#include <QSet>

namespace
{
const QSet<QString> sensitiveKeys = {
    QStringLiteral("data"),
    QStringLiteral("samples"),
    QStringLiteral("signal"),
    QStringLiteral("signals"),
    QStringLiteral("eeg"),
    QStringLiteral("raw"),
    QStringLiteral("waveform"),
    QStringLiteral("timeseries"),
    QStringLiteral("time_series"),
    QStringLiteral("values"),
    QStringLiteral("array"),
    QStringLiteral("payload"),
};

constexpr int maxString = 256;
constexpr int maxListPreview = 8;

bool looksLikeNumericSeries(const QJsonArray &array)
{
    if (array.size() < 16) {
        return false;
    }
    const int n = qMin(array.size(), 16);
    for (int i = 0; i < n; ++i) {
        if (!array.at(i).isDouble()) {
            return false;
        }
    }
    return true;
}

QJsonObject summarizeSensitive(const QJsonValue &value)
{
    if (value.isArray()) {
        const QJsonArray array = value.toArray();
        return {
            {QStringLiteral("_redacted"), QStringLiteral("array")},
            {QStringLiteral("length"), array.size()},
        };
    }
    if (value.isObject()) {
        return {
            {QStringLiteral("_redacted"), QStringLiteral("object")},
            {QStringLiteral("keys"), static_cast<int>(value.toObject().size())},
        };
    }
    if (value.isString()) {
        return {
            {QStringLiteral("_redacted"), QStringLiteral("string")},
            {QStringLiteral("length"), value.toString().size()},
        };
    }
    if (value.isNull() || value.isUndefined()) {
        return {{QStringLiteral("_redacted"), QStringLiteral("null")}};
    }
    return {{QStringLiteral("_redacted"), QStringLiteral("value")}};
}
} // namespace

namespace IpcRedact
{

QJsonValue redact(const QJsonValue &value, const QString &key)
{
    if (!key.isEmpty() && sensitiveKeys.contains(key.toLower())) {
        return summarizeSensitive(value);
    }

    if (value.isObject()) {
        QJsonObject out;
        const QJsonObject object = value.toObject();
        for (auto it = object.begin(); it != object.end(); ++it) {
            out.insert(it.key(), redact(it.value(), it.key()));
        }
        return out;
    }

    if (value.isArray()) {
        const QJsonArray array = value.toArray();
        if (looksLikeNumericSeries(array)) {
            return QJsonObject{
                {QStringLiteral("_redacted"), QStringLiteral("numeric_series")},
                {QStringLiteral("length"), array.size()},
            };
        }

        QJsonArray out;
        const int n = qMin(array.size(), maxListPreview);
        for (int i = 0; i < n; ++i) {
            out.append(redact(array.at(i)));
        }
        if (array.size() > maxListPreview) {
            out.append(QJsonObject{
                {QStringLiteral("_truncated"), true},
                {QStringLiteral("remaining"), array.size() - maxListPreview},
            });
        }
        return out;
    }

    if (value.isString()) {
        const QString text = value.toString();
        if (text.size() > maxString) {
            return text.left(maxString)
                   + QStringLiteral("...<%1 more chars>").arg(text.size() - maxString);
        }
    }

    return value;
}

QString redactText(const QString &text)
{
    const QString trimmed = text.trimmed();
    if (trimmed.isEmpty()) {
        return trimmed;
    }

    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(trimmed.toUtf8(), &error);
    if (error.error == QJsonParseError::NoError && doc.isObject()) {
        const QJsonDocument redacted(redact(doc.object()).toObject());
        return QString::fromUtf8(redacted.toJson(QJsonDocument::Compact));
    }

    // Fallback: scrub obvious base64-ish or huge numeric dumps from free text.
    QString scrubbed = trimmed;
    static const QRegularExpression longNumbers(QStringLiteral(R"((?:-?\d+(?:\.\d+)?[\s,]+){16,})"));
    scrubbed.replace(longNumbers, QStringLiteral("[redacted numeric series]"));
    if (scrubbed.size() > 512) {
        scrubbed = scrubbed.left(512) + QStringLiteral("...<truncated>");
    }
    return scrubbed;
}

} // namespace IpcRedact

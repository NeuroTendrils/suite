#pragma once

#include <QObject>
#include <QString>
#include <QStringList>

// Locates the Python interpreter used to launch science workers.
// Preference order:
//   1. NEUROTENDRILS_PYTHON
//   2. Repo / app-adjacent .venv
//   3. python3 / python on PATH
class PythonRuntime final : public QObject
{
    Q_OBJECT

public:
    static PythonRuntime &instance();

    void initialize();

    [[nodiscard]] bool isAvailable() const;
    [[nodiscard]] QString interpreterPath() const;
    [[nodiscard]] QString venvDir() const;
    [[nodiscard]] QString sourceDescription() const;
    [[nodiscard]] QStringList discoveryCandidates() const;

signals:
    void changed();

private:
    PythonRuntime() = default;

    [[nodiscard]] static QStringList candidateInterpreters();
    [[nodiscard]] static bool looksLikePython(const QString &path);
    [[nodiscard]] static QString resolveExecutable(const QString &path);

    QString interpreterPath_;
    QString venvDir_;
    QString sourceDescription_;
    QStringList discoveryCandidates_;
};

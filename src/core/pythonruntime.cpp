#include "core/pythonruntime.hpp"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QProcess>
#include <QProcessEnvironment>
#include <QStandardPaths>

namespace
{
QString venvPythonUnder(const QString &venvRoot)
{
    if (venvRoot.isEmpty()) {
        return {};
    }

#ifdef Q_OS_WIN
    const QString scripts = QDir(venvRoot).filePath(QStringLiteral("Scripts/python.exe"));
#else
    const QString scripts = QDir(venvRoot).filePath(QStringLiteral("bin/python"));
    const QString scripts3 = QDir(venvRoot).filePath(QStringLiteral("bin/python3"));
    if (QFileInfo::exists(scripts3)) {
        return scripts3;
    }
#endif
    return scripts;
}

QStringList nearbyVenvRoots()
{
    QStringList roots;

    const QString appDir = QCoreApplication::applicationDirPath();
    
    roots << QDir(appDir).filePath(QStringLiteral(".venv"));
    roots << QDir(appDir).filePath(QStringLiteral("../.venv"));
    roots << QDir(appDir).filePath(QStringLiteral("../../.venv"));
    roots << QDir(appDir).filePath(QStringLiteral("../../../.venv"));
    roots << QDir(appDir).filePath(QStringLiteral("../../../../.venv"));

    // When launched from a build tree, also check CWD and its parents.
    QDir cwd = QDir::current();
    for (int i = 0; i < 5; ++i) {
        roots << cwd.filePath(QStringLiteral(".venv"));
        if (!cwd.cdUp()) {
            break;
        }
    }

    roots.removeDuplicates();
    return roots;
}
} // namespace

PythonRuntime &PythonRuntime::instance()
{
    static PythonRuntime runtime;
    return runtime;
}

void PythonRuntime::initialize()
{
    interpreterPath_.clear();
    venvDir_.clear();
    sourceDescription_.clear();
    discoveryCandidates_ = candidateInterpreters();

    for (const QString &candidate : discoveryCandidates_) {
        const QString resolved = resolveExecutable(candidate);
        if (!looksLikePython(resolved)) {
            continue;
        }

        interpreterPath_ = resolved;

        const QFileInfo info(resolved);
        const QDir binDir = info.absoluteDir();
#ifdef Q_OS_WIN
        if (binDir.dirName().compare(QStringLiteral("Scripts"), Qt::CaseInsensitive) == 0) {
            venvDir_ = QDir::cleanPath(binDir.absolutePath() + QStringLiteral("/.."));
        }
#else
        if (binDir.dirName() == QStringLiteral("bin")) {
            const QString cfg = QDir(binDir.absolutePath() + QStringLiteral("/.."))
                                    .filePath(QStringLiteral("pyvenv.cfg"));
            if (QFileInfo::exists(cfg)) {
                venvDir_ = QDir::cleanPath(binDir.absolutePath() + QStringLiteral("/.."));
            }
        }
#endif

        if (!venvDir_.isEmpty()) {
            sourceDescription_ = QStringLiteral("venv");
        } else if (QProcessEnvironment::systemEnvironment().contains(
                       QStringLiteral("NEUROTENDRILS_PYTHON"))) {
            sourceDescription_ = QStringLiteral("NEUROTENDRILS_PYTHON");
        } else {
            sourceDescription_ = QStringLiteral("PATH");
        }
        break;
    }

    emit changed();
}

bool PythonRuntime::isAvailable() const
{
    return !interpreterPath_.isEmpty();
}

QString PythonRuntime::interpreterPath() const
{
    return interpreterPath_;
}

QString PythonRuntime::venvDir() const
{
    return venvDir_;
}

QString PythonRuntime::sourceDescription() const
{
    return sourceDescription_;
}

QStringList PythonRuntime::discoveryCandidates() const
{
    return discoveryCandidates_;
}

QStringList PythonRuntime::candidateInterpreters()
{
    QStringList candidates;

    const QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
    const QString overridePython = env.value(QStringLiteral("NEUROTENDRILS_PYTHON"));
    if (!overridePython.isEmpty()) {
        candidates << overridePython;
    }

    const QString overrideVenv = env.value(QStringLiteral("NEUROTENDRILS_VENV"));
    if (!overrideVenv.isEmpty()) {
        candidates << venvPythonUnder(overrideVenv);
    }

    for (const QString &root : nearbyVenvRoots()) {
        candidates << venvPythonUnder(root);
    }

#ifdef Q_OS_WIN
    candidates << QStringLiteral("python") << QStringLiteral("python3");
#else
    candidates << QStringLiteral("python3") << QStringLiteral("python");
#endif

    candidates.removeAll(QString());
    candidates.removeDuplicates();
    return candidates;
}

bool PythonRuntime::looksLikePython(const QString &path)
{
    if (path.isEmpty()) {
        return false;
    }

    const QFileInfo info(path);
    if (info.isAbsolute() && !(info.exists() && info.isFile() && info.isExecutable())) {
#ifndef Q_OS_WIN
        return false;
#else
        if (!(info.exists() && info.isFile())) {
            return false;
        }
#endif
    }

    QProcess probe;
    probe.setProgram(path);
    probe.setArguments({QStringLiteral("-c"), QStringLiteral("import sys; print(sys.executable)")});
    probe.setProcessChannelMode(QProcess::SeparateChannels);
    probe.start();
    if (!probe.waitForStarted(2000)) {
        return false;
    }
    if (!probe.waitForFinished(3000)) {
        probe.kill();
        probe.waitForFinished(1000);
        return false;
    }
    return probe.exitStatus() == QProcess::NormalExit && probe.exitCode() == 0;
}

QString PythonRuntime::resolveExecutable(const QString &path)
{
    if (path.isEmpty()) {
        return {};
    }

    const QFileInfo info(path);
    if (info.isAbsolute()) {
        return QDir::cleanPath(info.absoluteFilePath());
    }

    const QString found = QStandardPaths::findExecutable(path);
    return found;
}

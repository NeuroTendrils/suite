#include "core/projectdir.hpp"

#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QMessageBox>
#include <QPushButton>
#include <QSettings>

namespace
{
constexpr auto rootSettingKey = "project/root";

const char *const subdirNames[] = {"plans", "datasets", "models", "runs", "learn"};

QString defaultRoot()
{
    return QDir::home().filePath(QStringLiteral("NeuroTendrils"));
}

// Resolves symlinks for existing paths so a link inside the project dir
// cannot point (and let file operations escape) outside of it.
QString resolvePath(const QString &path)
{
    const QString cleaned = QDir::cleanPath(QFileInfo(path).absoluteFilePath());
    const QFileInfo info(cleaned);
    const QString canonical = info.canonicalFilePath();
    return canonical.isEmpty() ? cleaned : canonical;
}
} // namespace

ProjectDir &ProjectDir::instance()
{
    static ProjectDir projectDir;
    return projectDir;
}

void ProjectDir::initialize(QWidget *dialogParent)
{
    QSettings settings;
    QString root = settings.value(rootSettingKey).toString();

    if (root.isEmpty()) {
        QMessageBox box(dialogParent);
        box.setWindowTitle(tr("Choose Project Folder"));
        box.setText(tr("NeuroTendrils keeps your plans, datasets, models, runs, and "
                       "lessons together in one project folder."));
        box.setInformativeText(tr("Use the default folder %1, or choose another location.")
                                   .arg(QDir::toNativeSeparators(defaultRoot())));
        QAbstractButton *useDefault = box.addButton(tr("Use Default"), QMessageBox::AcceptRole);
        QAbstractButton *choose = box.addButton(tr("Choose…"), QMessageBox::ActionRole);
        box.setDefaultButton(qobject_cast<QPushButton *>(useDefault));
        box.exec();

        root = defaultRoot();
        if (box.clickedButton() == choose) {
            const QString picked = QFileDialog::getExistingDirectory(
                dialogParent, tr("Choose Project Folder"), QDir::homePath());
            if (!picked.isEmpty()) {
                root = picked;
            }
        }
        settings.setValue(rootSettingKey, root);
    }

    root_ = root;

    QDir rootDir(root_);
    rootDir.mkpath(QStringLiteral("."));
    for (const auto *subdir : subdirNames) {
        rootDir.mkpath(QLatin1String(subdir));
    }

    if (!rootDir.exists()) {
        QMessageBox::warning(dialogParent, tr("Project Folder Unavailable"),
                             tr("The project folder %1 could not be created. Please choose "
                                "a different location in Settings.")
                                 .arg(QDir::toNativeSeparators(root_)));
    }

    emit rootChanged(root_);
}

QString ProjectDir::root() const
{
    return root_;
}

QString ProjectDir::plansDir() const
{
    return QDir(root_).filePath(QStringLiteral("plans"));
}

QString ProjectDir::datasetsDir() const
{
    return QDir(root_).filePath(QStringLiteral("datasets"));
}

QString ProjectDir::modelsDir() const
{
    return QDir(root_).filePath(QStringLiteral("models"));
}

QString ProjectDir::runsDir() const
{
    return QDir(root_).filePath(QStringLiteral("runs"));
}

QString ProjectDir::learnDir() const
{
    return QDir(root_).filePath(QStringLiteral("learn"));
}

bool ProjectDir::contains(const QString &path) const
{
    if (root_.isEmpty() || path.isEmpty()) {
        return false;
    }

    const QString resolved = resolvePath(path);
    const QString resolvedRoot = resolvePath(root_);

#ifdef Q_OS_WIN
    constexpr Qt::CaseSensitivity caseSensitivity = Qt::CaseInsensitive;
#else
    constexpr Qt::CaseSensitivity caseSensitivity = Qt::CaseSensitive;
#endif

    return resolved.compare(resolvedRoot, caseSensitivity) == 0
           || resolved.startsWith(resolvedRoot + QLatin1Char('/'), caseSensitivity);
}

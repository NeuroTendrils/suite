#pragma once

#include <QObject>
#include <QString>

class QWidget;

// Owns the on-disk project folder (default ~/NeuroTendrils) that holds
// plans/, datasets/, models/, runs/, and learn/. All file I/O crossing
// the worker IPC boundary must stay inside this folder; use contains()
// to enforce that.
class ProjectDir final : public QObject
{
    Q_OBJECT

public:
    static ProjectDir &instance();

    // Resolves the project root (asking the user on first run), creates
    // the standard subdirectories, and persists the choice.
    void initialize(QWidget *dialogParent = nullptr);

    [[nodiscard]] QString root() const;
    [[nodiscard]] QString plansDir() const;
    [[nodiscard]] QString datasetsDir() const;
    [[nodiscard]] QString modelsDir() const;
    [[nodiscard]] QString runsDir() const;
    [[nodiscard]] QString learnDir() const;

    // Sandbox helper: true if the given path (cleaned, absolute, and
    // with symlinks resolved when it exists) is the project root or
    // located inside it.
    [[nodiscard]] bool contains(const QString &path) const;

signals:
    void rootChanged(const QString &root);

private:
    ProjectDir() = default;

    QString root_;
};

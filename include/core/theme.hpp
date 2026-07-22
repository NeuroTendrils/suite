#pragma once

#include <QColor>
#include <QObject>
#include <QPalette>

class QApplication;

enum class ThemeMode
{
    System,
    Light,
    Dark
};

class Theme final : public QObject
{
    Q_OBJECT

public:
    static Theme &instance();

    void initialize(QApplication &application);
    [[nodiscard]] ThemeMode mode() const;
    [[nodiscard]] bool isDark() const;
    [[nodiscard]] QColor accentColor() const;
    [[nodiscard]] QColor textColor() const;
    [[nodiscard]] QColor mutedTextColor() const;
    [[nodiscard]] QColor borderColor() const;

public slots:
    void setMode(ThemeMode mode);

signals:
    void modeChanged(ThemeMode mode);
    void changed();

private:
    Theme();

    [[nodiscard]] bool systemUsesDarkColors() const;
    void apply();

    QApplication *application_ = nullptr;
    QPalette systemPalette_;
    ThemeMode mode_ = ThemeMode::System;
    bool applying_ = false;
    bool dark_ = false;
    QColor accent_;
    QColor text_;
    QColor mutedText_;
    QColor border_;
};

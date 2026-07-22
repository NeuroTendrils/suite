#pragma once

#include <QMainWindow>

class QLabel;
class QListWidget;
class QStackedWidget;
class QToolButton;
class SettingsDialog;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override;

private:
    void applyIcons();

    QListWidget *navigation_;
    QLabel *avatarLabel_;
    QToolButton *settingsButton_;
    QStackedWidget *pages_;
    SettingsDialog *settingsDialog_ = nullptr;
};

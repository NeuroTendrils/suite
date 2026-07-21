#pragma once

#include <QMainWindow>

class QListWidget;
class QStackedWidget;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);
    ~MainWindow() override;

private:
    QListWidget *navigation_;
    QStackedWidget *pages_;
};

#pragma once

#include <QDialog>

class QLabel;
class QListWidget;
class QPlainTextEdit;
class QPushButton;
class QStackedWidget;
class ThemePreviewCard;
class WorkerClient;

class SettingsDialog : public QDialog
{
    Q_OBJECT

public:
    explicit SettingsDialog(QWidget *parent = nullptr);

private:
    QWidget *createAppearancePane();
    QWidget *createInfoPane();
    QWidget *createDiagnosticsPane();
    void syncCards();
    void runIpcSelfTest();
    void appendDiagnosticLog(const QString &line);
    void setDiagnosticsBusy(bool busy);

    QListWidget *nav_;
    QStackedWidget *panes_;
    ThemePreviewCard *lightCard_ = nullptr;
    ThemePreviewCard *darkCard_ = nullptr;
    ThemePreviewCard *autoCard_ = nullptr;

    QPushButton *ipcTestButton_ = nullptr;
    QLabel *ipcStatusLabel_ = nullptr;
    QPlainTextEdit *ipcLog_ = nullptr;
    WorkerClient *workerClient_ = nullptr;
    enum class SelfTestStep { Idle, Ping, Echo };
    SelfTestStep selfTestStep_ = SelfTestStep::Idle;
};

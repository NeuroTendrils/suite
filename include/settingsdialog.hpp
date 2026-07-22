#pragma once

#include <QDialog>

class QListWidget;
class QStackedWidget;
class ThemePreviewCard;

class SettingsDialog : public QDialog
{
    Q_OBJECT

public:
    explicit SettingsDialog(QWidget *parent = nullptr);

private:
    QWidget *createAppearancePane();
    QWidget *createInfoPane();
    void syncCards();

    QListWidget *nav_;
    QStackedWidget *panes_;
    ThemePreviewCard *lightCard_ = nullptr;
    ThemePreviewCard *darkCard_ = nullptr;
    ThemePreviewCard *autoCard_ = nullptr;
};

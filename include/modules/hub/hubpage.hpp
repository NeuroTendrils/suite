#pragma once

#include <QWidget>

class QLabel;
class QPushButton;
class QVBoxLayout;
class SkeletonLoader;

class HubPage : public QWidget
{
    Q_OBJECT

public:
    explicit HubPage(QWidget *parent = nullptr);

protected:
    void showEvent(QShowEvent *event) override;

private:
    void refreshLibrary();
    void rebuildModelList();
    void onPublishPlaceholder();

    QLabel *libraryStatus_ = nullptr;
    SkeletonLoader *librarySkeleton_ = nullptr;
    QWidget *modelListHost_ = nullptr;
    QVBoxLayout *modelListLayout_ = nullptr;
    QLabel *cloudStatus_ = nullptr;
    QPushButton *signInPlaceholder_ = nullptr;
    QPushButton *refreshButton_ = nullptr;
};

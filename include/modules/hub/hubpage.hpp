#pragma once

#include "core/locallibrary.hpp"

#include <QWidget>

class QComboBox;
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
    enum class Filter {
        All,
        Plans,
        Datasets,
        Models,
    };

    void refreshLibrary();
    void rebuildList();
    void showDetail(const LocalLibrary::Entry &entry);
    void clearDetail();
    void onFilterChanged(int index);
    void onSharePlaceholder();
    void onPublishPlaceholder();
    void onSignInPlaceholder();
    [[nodiscard]] QVector<LocalLibrary::Entry> filteredEntries() const;
    [[nodiscard]] static QString formatSize(qint64 bytes);

    LocalLibrary::Index index_;
    Filter filter_ = Filter::All;
    QString selectedKey_;

    QComboBox *filterCombo_ = nullptr;
    QLabel *libraryStatus_ = nullptr;
    SkeletonLoader *librarySkeleton_ = nullptr;
    QWidget *listHost_ = nullptr;
    QVBoxLayout *listLayout_ = nullptr;
    QLabel *detailTitle_ = nullptr;
    QLabel *detailMeta_ = nullptr;
    QLabel *detailBody_ = nullptr;
    QPushButton *detailShareButton_ = nullptr;
    QPushButton *detailPublishButton_ = nullptr;
    QWidget *detailPanel_ = nullptr;
    QLabel *cloudStatus_ = nullptr;
    QLabel *usagePlaceholder_ = nullptr;
    QPushButton *signInPlaceholder_ = nullptr;
    QLabel *sharingStatus_ = nullptr;
    QComboBox *visibilityCombo_ = nullptr;
    QPushButton *shareHfButton_ = nullptr;
    QPushButton *shareKaggleButton_ = nullptr;
    QPushButton *refreshButton_ = nullptr;
};

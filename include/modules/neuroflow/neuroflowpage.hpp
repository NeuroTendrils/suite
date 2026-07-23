#pragma once

#include <QWidget>

class QLabel;
class QPushButton;
class QStackedWidget;
class SkeletonLoader;

class NeuroFlowPage : public QWidget
{
    Q_OBJECT

public:
    explicit NeuroFlowPage(QWidget *parent = nullptr);

    [[nodiscard]] QString currentDatasetPath() const;

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    void importRecording();
    void clearRecording();
    void setDatasetPath(const QString &path, bool copied);
    void refreshIcons();
    void updateElidedTexts();
    [[nodiscard]] static QString formatFileSize(qint64 bytes);

    QStackedWidget *recordingStack_ = nullptr;
    QLabel *emptyIconLabel_ = nullptr;
    QLabel *emptyHint_ = nullptr;
    QLabel *fileIconLabel_ = nullptr;
    QLabel *fileNameLabel_ = nullptr;
    QLabel *fileMetaLabel_ = nullptr;
    QLabel *filePathLabel_ = nullptr;
    QLabel *fileBadge_ = nullptr;
    QPushButton *changeButton_ = nullptr;
    QPushButton *clearButton_ = nullptr;
    SkeletonLoader *fingerprintSkeleton_ = nullptr;
    QString datasetPath_;
    QString fullFileName_;
    QString fullFilePath_;
};

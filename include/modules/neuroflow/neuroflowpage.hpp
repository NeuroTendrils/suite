#pragma once

#include <QJsonObject>
#include <QWidget>

class QLabel;
class QPushButton;
class QStackedWidget;
class SkeletonLoader;
class WorkerClient;

class NeuroFlowPage : public QWidget
{
    Q_OBJECT

public:
    explicit NeuroFlowPage(QWidget *parent = nullptr);

    [[nodiscard]] QString currentDatasetPath() const;
    [[nodiscard]] QJsonObject currentFingerprint() const;

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    void importRecording();
    void clearRecording();
    void setDatasetPath(const QString &path, bool copied);
    void requestFingerprint();
    void cancelFingerprint();
    void onFingerprintFinished(bool ok,
                               const QJsonObject &result,
                               const QString &errorCode,
                               const QString &errorMessage);
    void setFingerprintIdle();
    void setFingerprintLoading();
    void setFingerprintReady(const QJsonObject &result);
    void setFingerprintError(const QString &message);
    void refreshIcons();
    void updateElidedTexts();
    [[nodiscard]] static QString formatFileSize(qint64 bytes);

    WorkerClient *workerClient_ = nullptr;
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
    QLabel *fingerprintStatus_ = nullptr;
    SkeletonLoader *fingerprintSkeleton_ = nullptr;
    QString datasetPath_;
    QString fullFileName_;
    QString fullFilePath_;
    QJsonObject fingerprint_;
};

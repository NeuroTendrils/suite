#pragma once

#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QWidget>

class QComboBox;
class QFormLayout;
class QLabel;
class QPushButton;
class QStackedWidget;
class QVBoxLayout;
class SkeletonLoader;
class WorkerClient;

class NeuroStudioPage : public QWidget
{
    Q_OBJECT

public:
    explicit NeuroStudioPage(QWidget *parent = nullptr);

    [[nodiscard]] QString currentDatasetPath() const;
    [[nodiscard]] QString currentTemplateId() const;
    [[nodiscard]] QJsonObject currentTemplateConfig() const;

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    void chooseDataset();
    void clearDataset();
    void setDatasetPath(const QString &path, const QString &kind);
    void setDatasetIdle();
    void refreshRecommendation();
    void rebuildTemplateList();
    void selectTemplate(const QString &templateId);
    void configureTemplate(const QString &templateId);
    void rebuildTuneForm();
    void syncTuneFormFromConfig();
    void applyTuneFormToConfig();
    void resetTuneDefaults();
    void startTraining();
    void cancelTraining();
    void startExport();
    void cancelExport();
    void onWorkerFinished(bool ok,
                          const QJsonObject &result,
                          const QString &errorCode,
                          const QString &errorMessage);
    void onWorkerEvent(const QString &requestId, const QString &name, const QJsonObject &data);
    void onWorkerLog(const QString &redactedLine);
    void setTrainIdle();
    void setTrainLoading();
    void setTrainReady(const QJsonObject &result);
    void setTrainError(const QString &message);
    void setExportIdle();
    void setExportLoading();
    void setExportReady(const QJsonObject &result);
    void setExportError(const QString &message);
    void updateTrainActionsEnabled();
    void updateExportActionsEnabled();
    void renderConfusion(const QJsonArray &matrix);
    void clearConfusion();
    [[nodiscard]] QJsonObject configFor(const QString &templateId) const;
    void refreshIcons();
    void updateElidedTexts();
    [[nodiscard]] static QString formatFileSize(qint64 bytes);
    [[nodiscard]] static QString kindLabel(const QString &kind);

    WorkerClient *workerClient_ = nullptr;
    QString activeOp_;
    bool trainBusy_ = false;
    bool exportBusy_ = false;
    QStackedWidget *datasetStack_ = nullptr;
    QLabel *emptyIconLabel_ = nullptr;
    QLabel *emptyHint_ = nullptr;
    QLabel *fileIconLabel_ = nullptr;
    QLabel *fileNameLabel_ = nullptr;
    QLabel *fileMetaLabel_ = nullptr;
    QLabel *filePathLabel_ = nullptr;
    QLabel *fileBadge_ = nullptr;
    QPushButton *changeButton_ = nullptr;
    QPushButton *clearButton_ = nullptr;
    QLabel *templatesStatus_ = nullptr;
    QWidget *templateListHost_ = nullptr;
    QVBoxLayout *templateListLayout_ = nullptr;
    QLabel *tuneStatus_ = nullptr;
    QWidget *tuneFormHost_ = nullptr;
    QFormLayout *tuneForm_ = nullptr;
    QPushButton *resetTuneButton_ = nullptr;
    QLabel *tuneError_ = nullptr;
    QHash<QString, QWidget *> tuneEditors_;
    bool tuneUpdating_ = false;
    QComboBox *deviceCombo_ = nullptr;
    QPushButton *trainButton_ = nullptr;
    QPushButton *cancelTrainButton_ = nullptr;
    QLabel *trainStatus_ = nullptr;
    SkeletonLoader *trainSkeleton_ = nullptr;
    QLabel *liveMetrics_ = nullptr;
    QLabel *finalMetrics_ = nullptr;
    QLabel *trainLog_ = nullptr;
    QLabel *artifactsLabel_ = nullptr;
    QWidget *confusionHost_ = nullptr;
    QVBoxLayout *confusionLayout_ = nullptr;
    QComboBox *exportFormatCombo_ = nullptr;
    QPushButton *exportButton_ = nullptr;
    QPushButton *cancelExportButton_ = nullptr;
    QPushButton *publishPlaceholderButton_ = nullptr;
    QLabel *exportStatus_ = nullptr;
    SkeletonLoader *exportSkeleton_ = nullptr;
    QLabel *exportResult_ = nullptr;
    QString datasetPath_;
    QString fullFileName_;
    QString fullFilePath_;
    QString datasetKind_;
    QString suggestedTemplateId_;
    QString selectedTemplateId_;
    QString trainRunDir_;
    QString exportModelDir_;
    QJsonObject lastTrainResult_;
    QHash<QString, QJsonObject> templateConfigs_;
};

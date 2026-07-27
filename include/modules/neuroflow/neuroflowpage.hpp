#pragma once

#include "core/plangenerator.hpp"

#include <QJsonObject>
#include <QWidget>

class QLabel;
class QPushButton;
class QStackedWidget;
class QVBoxLayout;
class QWidget;
class SkeletonLoader;
class WorkerClient;

class NeuroFlowPage : public QWidget
{
    Q_OBJECT

public:
    explicit NeuroFlowPage(QWidget *parent = nullptr);

    [[nodiscard]] QString currentDatasetPath() const;
    [[nodiscard]] QJsonObject currentFingerprint() const;
    [[nodiscard]] PlanGenerator::Plan currentPlan() const;

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    enum class WorkerOp {
        None,
        Fingerprint,
        Run,
    };

    void importRecording();
    void clearRecording();
    void setDatasetPath(const QString &path, bool copied);
    void requestFingerprint();
    void cancelWorker();
    void onWorkerFinished(bool ok,
                          const QJsonObject &result,
                          const QString &errorCode,
                          const QString &errorMessage);
    void onWorkerLog(const QString &redactedLine);
    void onWorkerEvent(const QString &requestId, const QString &name, const QJsonObject &data);
    void setFingerprintIdle();
    void setFingerprintLoading();
    void setFingerprintReady(const QJsonObject &result);
    void setFingerprintError(const QString &message);
    void populateFingerprintCard(const QJsonObject &result);
    void regeneratePlan();
    void clearPlan();
    void setPlanIdle();
    void setPlanReady(const PlanGenerator::Plan &plan);
    void rebuildPlanList(const PlanGenerator::Plan &plan);
    void clearPlanList();
    void editPlanStep(int index);
    void movePlanStep(int index, int delta);
    void removePlanStep(int index);
    void addPlanStep();
    void savePlan();
    void loadPlan();
    void runPlan();
    void setRunIdle();
    void setRunLoading();
    void setRunReady(const QJsonObject &result, const QString &outputPath, const QString &metaPath);
    void setRunError(const QString &message);
    void refreshPlanUi();
    void refreshIcons();
    void updateElidedTexts();
    void updateRunActionsEnabled();
    [[nodiscard]] static QString formatFileSize(qint64 bytes);
    [[nodiscard]] static QString formatDuration(double seconds);
    [[nodiscard]] static QString formatHz(double hz);
    [[nodiscard]] static QString formatOptionalHz(const QJsonValue &value);
    [[nodiscard]] static QString formatStepParams(const QJsonObject &params);
    [[nodiscard]] static PlanGenerator::Step makeCatalogStep(const QString &stepId,
                                                            const QString &rationale = {});

    WorkerClient *workerClient_ = nullptr;
    WorkerOp pendingOp_ = WorkerOp::None;
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
    QWidget *fingerprintCard_ = nullptr;
    QLabel *fpChannelsValue_ = nullptr;
    QLabel *fpSfreqValue_ = nullptr;
    QLabel *fpDurationValue_ = nullptr;
    QLabel *fpMontageValue_ = nullptr;
    QLabel *fpFiltersValue_ = nullptr;
    QLabel *fpChannelNames_ = nullptr;
    QLabel *planStatus_ = nullptr;
    QWidget *planListHost_ = nullptr;
    QVBoxLayout *planListLayout_ = nullptr;
    QWidget *planActions_ = nullptr;
    QPushButton *addStepButton_ = nullptr;
    QPushButton *savePlanButton_ = nullptr;
    QPushButton *loadPlanButton_ = nullptr;
    QPushButton *runPlanButton_ = nullptr;
    QPushButton *cancelRunButton_ = nullptr;
    QLabel *runStatus_ = nullptr;
    SkeletonLoader *runSkeleton_ = nullptr;
    QLabel *runResult_ = nullptr;
    QLabel *runLog_ = nullptr;
    QString datasetPath_;
    QString fullFileName_;
    QString fullFilePath_;
    QString planPath_;
    QString runOutputPath_;
    QString runMetadataPath_;
    bool planUserOwned_ = false;
    QJsonObject fingerprint_;
    PlanGenerator::Plan plan_;
};

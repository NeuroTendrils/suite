#pragma once

#include <QHash>
#include <QJsonObject>
#include <QWidget>

class QLabel;
class QPushButton;
class QStackedWidget;
class QVBoxLayout;

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
    [[nodiscard]] QJsonObject configFor(const QString &templateId) const;
    void refreshIcons();
    void updateElidedTexts();
    [[nodiscard]] static QString formatFileSize(qint64 bytes);
    [[nodiscard]] static QString kindLabel(const QString &kind);

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
    QString datasetPath_;
    QString fullFileName_;
    QString fullFilePath_;
    QString datasetKind_;
    QString suggestedTemplateId_;
    QString selectedTemplateId_;
    QHash<QString, QJsonObject> templateConfigs_;
};

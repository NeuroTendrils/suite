#pragma once

#include <QWidget>

class QLabel;
class QPushButton;
class QStackedWidget;

class NeuroStudioPage : public QWidget
{
    Q_OBJECT

public:
    explicit NeuroStudioPage(QWidget *parent = nullptr);

    [[nodiscard]] QString currentDatasetPath() const;

protected:
    void resizeEvent(QResizeEvent *event) override;

private:
    void chooseDataset();
    void clearDataset();
    void setDatasetPath(const QString &path, const QString &kind);
    void setDatasetIdle();
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
    QString datasetPath_;
    QString fullFileName_;
    QString fullFilePath_;
    QString datasetKind_;
};

#pragma once

#include <QDialog>
#include <QHash>
#include <QJsonObject>
#include <QString>

class QFormLayout;
class QLabel;
class QWidget;

// Modal editor for one NeuroStudio template (hyperparams + train knobs).
class TemplateEditDialog : public QDialog
{
    Q_OBJECT

public:
    TemplateEditDialog(const QString &templateId,
                       const QJsonObject &config,
                       QWidget *parent = nullptr);

    [[nodiscard]] QJsonObject config() const;

private:
    void buildForm(const QJsonObject &config);
    [[nodiscard]] QJsonObject collectConfig() const;
    bool applyValidation();

    QString templateId_;
    QFormLayout *form_ = nullptr;
    QLabel *errorLabel_ = nullptr;
    QHash<QString, QWidget *> editors_;
};

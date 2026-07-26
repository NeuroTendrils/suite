#pragma once

#include <QDialog>
#include <QHash>
#include <QJsonObject>
#include <QString>

class QCheckBox;
class QComboBox;
class QDoubleSpinBox;
class QFormLayout;
class QLabel;
class QLineEdit;
class QWidget;

// Modal editor for one plan step, fields driven by StepCatalog schemas.
class StepEditDialog : public QDialog
{
    Q_OBJECT

public:
    StepEditDialog(const QString &stepId,
                   const QString &title,
                   const QJsonObject &params,
                   QWidget *parent = nullptr);

    [[nodiscard]] QJsonObject params() const;

private:
    void buildForm(const QJsonObject &params);
    [[nodiscard]] QJsonObject collectParams() const;
    bool applyValidation();

    QString stepId_;
    QFormLayout *form_ = nullptr;
    QLabel *errorLabel_ = nullptr;
    QHash<QString, QWidget *> editors_;
};

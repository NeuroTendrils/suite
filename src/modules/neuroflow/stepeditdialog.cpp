#include "modules/neuroflow/stepeditdialog.hpp"

#include "core/stepcatalog.hpp"

#include <QCheckBox>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QVBoxLayout>
#include <QtGlobal>

StepEditDialog::StepEditDialog(const QString &stepId,
                               const QString &title,
                               const QJsonObject &params,
                               QWidget *parent)
    : QDialog(parent)
    , stepId_(stepId)
{
    setWindowTitle(tr("Edit step: %1").arg(title));
    setModal(true);
    setMinimumWidth(380);

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 16, 16, 16);
    root->setSpacing(12);

    auto *intro = new QLabel(tr("Adjust parameters for this preprocessing step."), this);
    intro->setObjectName(QStringLiteral("upcomingCaption"));
    intro->setWordWrap(true);

    auto *formHost = new QWidget(this);
    form_ = new QFormLayout(formHost);
    form_->setContentsMargins(0, 0, 0, 0);
    form_->setHorizontalSpacing(12);
    form_->setVerticalSpacing(10);
    form_->setFieldGrowthPolicy(QFormLayout::ExpandingFieldsGrow);

    errorLabel_ = new QLabel(this);
    errorLabel_->setObjectName(QStringLiteral("stepEditError"));
    errorLabel_->setWordWrap(true);
    errorLabel_->setVisible(false);

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    connect(buttons, &QDialogButtonBox::accepted, this, [this]() {
        if (applyValidation()) {
            accept();
        }
    });
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);

    root->addWidget(intro);
    root->addWidget(formHost);
    root->addWidget(errorLabel_);
    root->addWidget(buttons);

    buildForm(params);
}

void StepEditDialog::buildForm(const QJsonObject &params)
{
    const StepCatalog::StepDefinition *def = StepCatalog::find(stepId_);
    if (def == nullptr) {
        errorLabel_->setText(tr("Unknown step “%1”.").arg(stepId_));
        errorLabel_->setVisible(true);
        return;
    }

    for (const StepCatalog::ParamSchema &schema : def->params) {
        const QJsonValue current = params.contains(schema.id) ? params.value(schema.id)
                                                              : schema.defaultValue;
        QWidget *editor = nullptr;

        switch (schema.type) {
        case StepCatalog::ParamType::Boolean: {
            auto *box = new QCheckBox(this);
            box->setChecked(current.toBool(schema.defaultValue.toBool()));
            editor = box;
            break;
        }
        case StepCatalog::ParamType::Enum: {
            auto *combo = new QComboBox(this);
            combo->addItems(schema.enumValues);
            const QString value = current.toString(schema.defaultValue.toString());
            const int index = combo->findText(value);
            combo->setCurrentIndex(index >= 0 ? index : 0);
            editor = combo;
            break;
        }
        case StepCatalog::ParamType::String: {
            auto *line = new QLineEdit(this);
            line->setText(current.toString(schema.defaultValue.toString()));
            line->setPlaceholderText(schema.required ? tr("Required") : tr("Optional"));
            editor = line;
            break;
        }
        case StepCatalog::ParamType::Integer:
        case StepCatalog::ParamType::Number: {
            auto *spin = new QDoubleSpinBox(this);
            spin->setDecimals(schema.type == StepCatalog::ParamType::Integer ? 0 : 3);
            spin->setMinimum(schema.minimum.value_or(-1.0e9));
            spin->setMaximum(schema.maximum.value_or(1.0e9));
            spin->setSingleStep(schema.type == StepCatalog::ParamType::Integer ? 1.0 : 0.1);
            if (!schema.unit.isEmpty()) {
                spin->setSuffix(QStringLiteral(" %1").arg(schema.unit));
            }
            spin->setValue(current.toDouble(schema.defaultValue.toDouble()));
            editor = spin;
            break;
        }
        }

        if (editor == nullptr) {
            continue;
        }

        editors_.insert(schema.id, editor);

        auto *label = new QLabel(schema.label, this);
        if (!schema.help.isEmpty()) {
            label->setToolTip(schema.help);
            editor->setToolTip(schema.help);
        }
        form_->addRow(label, editor);
    }
}

QJsonObject StepEditDialog::collectParams() const
{
    QJsonObject params;
    const StepCatalog::StepDefinition *def = StepCatalog::find(stepId_);
    if (def == nullptr) {
        return params;
    }

    for (const StepCatalog::ParamSchema &schema : def->params) {
        QWidget *editor = editors_.value(schema.id, nullptr);
        if (editor == nullptr) {
            continue;
        }

        switch (schema.type) {
        case StepCatalog::ParamType::Boolean:
            params.insert(schema.id, qobject_cast<QCheckBox *>(editor)->isChecked());
            break;
        case StepCatalog::ParamType::Enum:
            params.insert(schema.id, qobject_cast<QComboBox *>(editor)->currentText());
            break;
        case StepCatalog::ParamType::String:
            params.insert(schema.id, qobject_cast<QLineEdit *>(editor)->text());
            break;
        case StepCatalog::ParamType::Integer: {
            const double value = qobject_cast<QDoubleSpinBox *>(editor)->value();
            params.insert(schema.id, static_cast<int>(qRound(value)));
            break;
        }
        case StepCatalog::ParamType::Number:
            params.insert(schema.id, qobject_cast<QDoubleSpinBox *>(editor)->value());
            break;
        }
    }
    return params;
}

QJsonObject StepEditDialog::params() const
{
    return collectParams();
}

bool StepEditDialog::applyValidation()
{
    const QJsonObject next = collectParams();
    const QString error = StepCatalog::validateParams(stepId_, next);
    if (!error.isEmpty()) {
        errorLabel_->setText(error);
        errorLabel_->setVisible(true);
        return false;
    }
    errorLabel_->clear();
    errorLabel_->setVisible(false);
    return true;
}

#include "modules/neurostudio/templateeditdialog.hpp"

#include "core/templatecatalog.hpp"

#include <QCheckBox>
#include <QComboBox>
#include <QDialogButtonBox>
#include <QDoubleSpinBox>
#include <QFormLayout>
#include <QLabel>
#include <QLineEdit>
#include <QVBoxLayout>
#include <QtGlobal>

namespace
{

void addSectionLabel(QFormLayout *form, const QString &title, QWidget *parent)
{
    auto *label = new QLabel(title, parent);
    label->setObjectName(QStringLiteral("groupLabel"));
    form->addRow(label);
}

} // namespace

TemplateEditDialog::TemplateEditDialog(const QString &templateId,
                                       const QJsonObject &config,
                                       QWidget *parent)
    : QDialog(parent)
    , templateId_(templateId)
{
    const TemplateCatalog::TemplateDefinition *def = TemplateCatalog::find(templateId_);
    const QString title = def != nullptr ? def->title : templateId_;
    setWindowTitle(tr("Configure: %1").arg(title));
    setModal(true);
    setMinimumWidth(420);

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 16, 16, 16);
    root->setSpacing(12);

    auto *intro = new QLabel(
        tr("Edit model hyperparams and train settings for this template."), this);
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

    buildForm(config);
}

void TemplateEditDialog::buildForm(const QJsonObject &config)
{
    const TemplateCatalog::TemplateDefinition *def = TemplateCatalog::find(templateId_);
    if (def == nullptr) {
        errorLabel_->setText(tr("Unknown template “%1”.").arg(templateId_));
        errorLabel_->setVisible(true);
        return;
    }

    auto addParams = [this, &config](const QVector<TemplateCatalog::ParamSchema> &schemas) {
        for (const TemplateCatalog::ParamSchema &schema : schemas) {
            const QJsonValue current = config.contains(schema.id) ? config.value(schema.id)
                                                                  : schema.defaultValue;
            QWidget *editor = nullptr;

            switch (schema.type) {
            case TemplateCatalog::ParamType::Boolean: {
                auto *box = new QCheckBox(this);
                box->setChecked(current.toBool(schema.defaultValue.toBool()));
                editor = box;
                break;
            }
            case TemplateCatalog::ParamType::Enum: {
                auto *combo = new QComboBox(this);
                combo->addItems(schema.enumValues);
                const QString value = current.toString(schema.defaultValue.toString());
                const int index = combo->findText(value);
                combo->setCurrentIndex(index >= 0 ? index : 0);
                editor = combo;
                break;
            }
            case TemplateCatalog::ParamType::String: {
                auto *line = new QLineEdit(this);
                line->setText(current.toString(schema.defaultValue.toString()));
                line->setPlaceholderText(schema.required ? tr("Required") : tr("Optional"));
                editor = line;
                break;
            }
            case TemplateCatalog::ParamType::Integer:
            case TemplateCatalog::ParamType::Number: {
                auto *spin = new QDoubleSpinBox(this);
                spin->setDecimals(schema.type == TemplateCatalog::ParamType::Integer ? 0 : 6);
                spin->setMinimum(schema.minimum.value_or(-1.0e9));
                spin->setMaximum(schema.maximum.value_or(1.0e9));
                spin->setSingleStep(schema.type == TemplateCatalog::ParamType::Integer ? 1.0
                                                                                       : 0.0001);
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
    };

    addSectionLabel(form_, tr("Model"), this);
    addParams(def->hyperparams);
    addSectionLabel(form_, tr("Train"), this);
    addParams(def->train);
}

QJsonObject TemplateEditDialog::collectConfig() const
{
    QJsonObject config;
    const TemplateCatalog::TemplateDefinition *def = TemplateCatalog::find(templateId_);
    if (def == nullptr) {
        return config;
    }

    auto collect = [this, &config](const QVector<TemplateCatalog::ParamSchema> &schemas) {
        for (const TemplateCatalog::ParamSchema &schema : schemas) {
            QWidget *editor = editors_.value(schema.id, nullptr);
            if (editor == nullptr) {
                continue;
            }
            switch (schema.type) {
            case TemplateCatalog::ParamType::Boolean:
                config.insert(schema.id, qobject_cast<QCheckBox *>(editor)->isChecked());
                break;
            case TemplateCatalog::ParamType::Enum:
                config.insert(schema.id, qobject_cast<QComboBox *>(editor)->currentText());
                break;
            case TemplateCatalog::ParamType::String:
                config.insert(schema.id, qobject_cast<QLineEdit *>(editor)->text());
                break;
            case TemplateCatalog::ParamType::Integer: {
                const double value = qobject_cast<QDoubleSpinBox *>(editor)->value();
                config.insert(schema.id, static_cast<int>(qRound(value)));
                break;
            }
            case TemplateCatalog::ParamType::Number:
                config.insert(schema.id, qobject_cast<QDoubleSpinBox *>(editor)->value());
                break;
            }
        }
    };

    collect(def->hyperparams);
    collect(def->train);
    return config;
}

QJsonObject TemplateEditDialog::config() const
{
    return collectConfig();
}

bool TemplateEditDialog::applyValidation()
{
    const QJsonObject next = collectConfig();
    const QString error = TemplateCatalog::validateConfig(templateId_, next);
    if (!error.isEmpty()) {
        errorLabel_->setText(error);
        errorLabel_->setVisible(true);
        return false;
    }
    errorLabel_->clear();
    errorLabel_->setVisible(false);
    return true;
}

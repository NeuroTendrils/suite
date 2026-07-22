#pragma once

#include <QWidget>

class PageHeader : public QWidget
{
    Q_OBJECT

public:
    explicit PageHeader(const QString &title, const QString &subtitle,
                        QWidget *parent = nullptr);
};

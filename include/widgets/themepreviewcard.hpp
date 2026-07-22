#pragma once

#include <QAbstractButton>

// A clickable card showing a miniature window preview of a theme
// (light, dark, or auto/system), with a caption underneath.
class ThemePreviewCard : public QAbstractButton
{
    Q_OBJECT

public:
    enum class Preview
    {
        Light,
        Dark,
        Auto
    };

    ThemePreviewCard(Preview preview, const QString &caption, QWidget *parent = nullptr);

    [[nodiscard]] QSize sizeHint() const override;

protected:
    void paintEvent(QPaintEvent *event) override;

private:
    Preview preview_;
};

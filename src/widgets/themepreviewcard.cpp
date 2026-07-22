#include "widgets/themepreviewcard.hpp"

#include "core/theme.hpp"

#include <QPainter>
#include <QPainterPath>

namespace
{
// Fixed depiction colors: the previews illustrate the light and dark
// themes themselves, independent of the currently active theme.
const QColor previewLightBackground(0xff, 0xff, 0xff);
const QColor previewLightBorder(0xe3, 0xe5, 0xea);
const QColor previewLightLine(0xd9, 0xdc, 0xe3);
const QColor previewLightBar(0x37, 0x58, 0xbc);
const QColor previewDarkBackground(0x10, 0x13, 0x1c);
const QColor previewDarkBorder(0x2a, 0x2f, 0x3c);
const QColor previewDarkLine(0x23, 0x29, 0x38);
const QColor previewDarkBar(0x77, 0x95, 0xf8);
} // namespace

ThemePreviewCard::ThemePreviewCard(Preview preview, const QString &caption, QWidget *parent)
    : QAbstractButton(parent)
    , preview_(preview)
{
    setText(caption);
    setCheckable(true);
    setCursor(Qt::PointingHandCursor);
    setFixedSize(sizeHint());

    connect(&Theme::instance(), &Theme::changed, this, qOverload<>(&QWidget::update));
}

QSize ThemePreviewCard::sizeHint() const
{
    return {176, 148};
}

void ThemePreviewCard::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event);

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const Theme &theme = Theme::instance();

    // Card frame.
    const QRectF cardRect = QRectF(rect()).adjusted(1.5, 1.5, -1.5, -1.5);
    if (isChecked()) {
        QColor tint = theme.accentColor();
        tint.setAlpha(theme.isDark() ? 36 : 22);
        painter.setBrush(tint);
        painter.setPen(QPen(theme.accentColor(), 2.0));
    } else {
        painter.setBrush(Qt::NoBrush);
        painter.setPen(QPen(theme.borderColor(), 1.0));
    }
    painter.drawRoundedRect(cardRect, 10.0, 10.0);

    // Miniature window preview.
    const QRectF previewRect = cardRect.adjusted(14.0, 14.0, -14.0, -38.0);
    QPainterPath clip;
    clip.addRoundedRect(previewRect, 6.0, 6.0);
    painter.save();
    painter.setClipPath(clip);

    const bool lightBase = preview_ != Preview::Dark;
    painter.fillRect(previewRect, lightBase ? previewLightBackground : previewDarkBackground);

    if (preview_ == Preview::Auto) {
        // Half light, half dark.
        QRectF darkHalf = previewRect;
        darkHalf.setLeft(previewRect.center().x());
        painter.fillRect(darkHalf, previewDarkBackground);
    } else {
        const QColor bar = lightBase ? previewLightBar : previewDarkBar;
        const QColor line = lightBase ? previewLightLine : previewDarkLine;
        const qreal x = previewRect.left() + 12.0;
        const qreal width = previewRect.width() - 24.0;

        painter.setPen(Qt::NoPen);
        painter.setBrush(bar);
        painter.drawRoundedRect(QRectF(x, previewRect.top() + 14.0, width, 7.0), 3.5, 3.5);
        painter.setBrush(line);
        painter.drawRoundedRect(QRectF(x, previewRect.top() + 29.0, width, 5.0), 2.5, 2.5);
        painter.drawRoundedRect(QRectF(x, previewRect.top() + 42.0, width * 0.6, 5.0), 2.5,
                                2.5);
    }

    painter.restore();
    painter.setPen(
        QPen(preview_ == Preview::Dark ? previewDarkBorder : previewLightBorder, 1.0));
    painter.setBrush(Qt::NoBrush);
    painter.drawRoundedRect(previewRect, 6.0, 6.0);

    // Caption.
    painter.setPen(theme.textColor());
    QRectF captionRect(cardRect.left(), previewRect.bottom(), cardRect.width(),
                       cardRect.bottom() - previewRect.bottom());
    painter.drawText(captionRect, Qt::AlignCenter, text());
}

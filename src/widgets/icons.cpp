#include "widgets/icons.hpp"

#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPixmap>

namespace
{

// All glyphs are drawn in a 24x24 logical coordinate space.
void paintGlyph(QPainter &painter, icons::Glyph glyph, const QColor &color)
{
    QPen stroke(color, 1.8, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin);

    switch (glyph) {
    case icons::Glyph::Flow: {
        painter.setPen(stroke);
        painter.setBrush(Qt::NoBrush);
        QPainterPath branches;
        branches.moveTo(7.8, 12.0);
        branches.lineTo(10.5, 12.0);
        branches.cubicTo(14.0, 12.0, 13.0, 5.5, 16.3, 5.5);
        branches.moveTo(10.5, 12.0);
        branches.cubicTo(14.0, 12.0, 13.0, 18.5, 16.3, 18.5);
        painter.drawPath(branches);

        painter.setPen(Qt::NoPen);
        painter.setBrush(color);
        painter.drawEllipse(QPointF(5.5, 12.0), 2.2, 2.2);
        painter.drawEllipse(QPointF(18.5, 5.5), 2.2, 2.2);
        painter.drawEllipse(QPointF(18.5, 18.5), 2.2, 2.2);
        break;
    }
    case icons::Glyph::Studio: {
        painter.setPen(Qt::NoPen);
        painter.setBrush(color);
        painter.drawRoundedRect(QRectF(4.5, 12.0, 3.2, 7.5), 1.4, 1.4);
        painter.drawRoundedRect(QRectF(10.4, 5.0, 3.2, 14.5), 1.4, 1.4);
        painter.drawRoundedRect(QRectF(16.3, 9.0, 3.2, 10.5), 1.4, 1.4);
        break;
    }
    case icons::Glyph::Learn: {
        painter.setPen(stroke);
        painter.setBrush(Qt::NoBrush);
        QPainterPath book;
        book.moveTo(12.0, 7.0);
        book.cubicTo(10.0, 5.4, 7.0, 5.4, 4.8, 6.6);
        book.lineTo(4.8, 17.6);
        book.cubicTo(7.0, 16.4, 10.0, 16.4, 12.0, 18.0);
        book.cubicTo(14.0, 16.4, 17.0, 16.4, 19.2, 17.6);
        book.lineTo(19.2, 6.6);
        book.cubicTo(17.0, 5.4, 14.0, 5.4, 12.0, 7.0);
        book.moveTo(12.0, 7.0);
        book.lineTo(12.0, 18.0);
        painter.drawPath(book);
        break;
    }
    case icons::Glyph::Hub: {
        painter.setPen(stroke);
        painter.setBrush(Qt::NoBrush);
        painter.drawRoundedRect(QRectF(4.5, 4.5, 6.4, 6.4), 1.8, 1.8);
        painter.drawRoundedRect(QRectF(13.1, 4.5, 6.4, 6.4), 1.8, 1.8);
        painter.drawRoundedRect(QRectF(4.5, 13.1, 6.4, 6.4), 1.8, 1.8);
        painter.drawRoundedRect(QRectF(13.1, 13.1, 6.4, 6.4), 1.8, 1.8);
        break;
    }
    case icons::Glyph::Settings: {
        // Sliders: three horizontal tracks with staggered knobs.
        painter.setPen(stroke);
        painter.drawLine(QPointF(4.5, 7.0), QPointF(19.5, 7.0));
        painter.drawLine(QPointF(4.5, 12.0), QPointF(19.5, 12.0));
        painter.drawLine(QPointF(4.5, 17.0), QPointF(19.5, 17.0));

        painter.setPen(Qt::NoPen);
        painter.setBrush(color);
        painter.drawEllipse(QPointF(9.0, 7.0), 2.3, 2.3);
        painter.drawEllipse(QPointF(15.0, 12.0), 2.3, 2.3);
        painter.drawEllipse(QPointF(7.5, 17.0), 2.3, 2.3);
        break;
    }
    }
}

QPixmap renderGlyph(icons::Glyph glyph, const QColor &color, int size, qreal devicePixelRatio)
{
    QPixmap pixmap(static_cast<int>(size * devicePixelRatio),
                   static_cast<int>(size * devicePixelRatio));
    pixmap.setDevicePixelRatio(devicePixelRatio);
    pixmap.fill(Qt::transparent);

    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.scale(size / 24.0, size / 24.0);
    paintGlyph(painter, glyph, color);
    painter.end();

    return pixmap;
}

} // namespace

namespace icons
{

QIcon icon(Glyph glyph, const QColor &normal, const QColor &selected)
{
    QIcon result;
    for (const int size : {16, 18, 20, 24, 32}) {
        for (const qreal devicePixelRatio : {1.0, 2.0}) {
            result.addPixmap(renderGlyph(glyph, normal, size, devicePixelRatio), QIcon::Normal);
            result.addPixmap(renderGlyph(glyph, selected, size, devicePixelRatio),
                             QIcon::Selected);
        }
    }
    return result;
}

QPixmap avatar(int size, qreal devicePixelRatio, const QColor &background,
               const QColor &foreground)
{
    QPixmap pixmap(static_cast<int>(size * devicePixelRatio),
                   static_cast<int>(size * devicePixelRatio));
    pixmap.setDevicePixelRatio(devicePixelRatio);
    pixmap.fill(Qt::transparent);

    QPainter painter(&pixmap);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.scale(size / 24.0, size / 24.0);

    // Circular badge, clipped so the silhouette's shoulders stay inside.
    QPainterPath circle;
    circle.addEllipse(QRectF(0.5, 0.5, 23.0, 23.0));
    painter.setClipPath(circle);
    painter.fillPath(circle, background);

    painter.setPen(Qt::NoPen);
    painter.setBrush(foreground);
    painter.drawEllipse(QPointF(12.0, 9.6), 3.6, 3.6);

    QPainterPath shoulders;
    shoulders.addRoundedRect(QRectF(4.8, 15.0, 14.4, 12.0), 6.4, 6.4);
    painter.fillPath(shoulders, foreground);

    painter.end();
    return pixmap;
}

} // namespace icons

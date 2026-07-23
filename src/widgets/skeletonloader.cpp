#include "widgets/skeletonloader.hpp"

#include "core/theme.hpp"

#include <QLinearGradient>
#include <QPainter>
#include <QPainterPath>

SkeletonLoader::SkeletonLoader(QWidget *parent)
    : QWidget(parent)
{
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setMinimumWidth(0);

    animation_.setStartValue(0.0);
    animation_.setEndValue(1.0);
    animation_.setDuration(1500);
    animation_.setLoopCount(-1);
    connect(&animation_, &QVariantAnimation::valueChanged, this, [this](const QVariant &value) {
        shimmer_ = value.toReal();
        update();
    });

    connect(&Theme::instance(), &Theme::changed, this, qOverload<>(&QWidget::update));
}

void SkeletonLoader::addBlock(qreal widthFactor, int height, int radius)
{
    blocks_.append({widthFactor, height, radius});
    updateGeometry();
    update();
}

QSize SkeletonLoader::sizeHint() const
{
    int height = 0;
    for (const Block &block : blocks_) {
        height += block.height;
    }
    if (!blocks_.isEmpty()) {
        height += blockSpacing * (static_cast<int>(blocks_.size()) - 1);
    }
    // Width must stay flexible so parent layouts can shrink on small windows.
    return {0, height};
}

QSize SkeletonLoader::minimumSizeHint() const
{
    return sizeHint();
}

void SkeletonLoader::paintEvent(QPaintEvent *event)
{
    Q_UNUSED(event);

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const Theme &theme = Theme::instance();
    QColor base = theme.borderColor();
    base.setAlpha(theme.isDark() ? 130 : 160);

    const QColor highlightColor(255, 255, 255, theme.isDark() ? 22 : 150);
    QColor transparent(highlightColor);
    transparent.setAlpha(0);

    // The shimmer band sweeps from left of the widget to past its right edge.
    const qreal bandWidth = width() * 0.35;
    const qreal bandStart = -bandWidth + shimmer_ * (width() + 2.0 * bandWidth);

    QLinearGradient gradient(bandStart, 0.0, bandStart + bandWidth, 0.0);
    gradient.setColorAt(0.0, transparent);
    gradient.setColorAt(0.5, highlightColor);
    gradient.setColorAt(1.0, transparent);

    int y = 0;
    for (const Block &block : blocks_) {
        QPainterPath path;
        path.addRoundedRect(QRectF(0, y, width() * block.widthFactor, block.height),
                            block.radius, block.radius);
        painter.fillPath(path, base);
        painter.fillPath(path, gradient);
        y += block.height + blockSpacing;
    }
}

void SkeletonLoader::showEvent(QShowEvent *event)
{
    QWidget::showEvent(event);
    animation_.start();
}

void SkeletonLoader::hideEvent(QHideEvent *event)
{
    QWidget::hideEvent(event);
    animation_.stop();
}

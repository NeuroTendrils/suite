#pragma once

#include <QList>
#include <QVariantAnimation>
#include <QWidget>

// Animated placeholder blocks shown while page content is loading.
// Blocks are stacked vertically; each has a width factor relative to
// the widget width. Animation runs only while the widget is visible.
class SkeletonLoader : public QWidget
{
    Q_OBJECT

public:
    explicit SkeletonLoader(QWidget *parent = nullptr);

    void addBlock(qreal widthFactor, int height, int radius = 6);

    [[nodiscard]] QSize sizeHint() const override;

protected:
    void paintEvent(QPaintEvent *event) override;
    void showEvent(QShowEvent *event) override;
    void hideEvent(QHideEvent *event) override;

private:
    struct Block
    {
        qreal widthFactor;
        int height;
        int radius;
    };

    static constexpr int blockSpacing = 14;

    QList<Block> blocks_;
    QVariantAnimation animation_;
    qreal shimmer_ = 0.0;
};

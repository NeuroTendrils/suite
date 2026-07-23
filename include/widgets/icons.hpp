#pragma once

#include <QColor>
#include <QIcon>
#include <QPixmap>

namespace icons
{

enum class Glyph
{
    Flow,
    Studio,
    Learn,
    Hub,
    Settings,
    File
};

// Renders a crisp, theme-tinted glyph. The selected color is used for
// QIcon::Selected (e.g. the active navigation item).
QIcon icon(Glyph glyph, const QColor &normal, const QColor &selected);

// Renders a circular placeholder avatar (person silhouette) at the
// given logical size, for the current screen's pixel ratio.
QPixmap avatar(int size, qreal devicePixelRatio, const QColor &background,
               const QColor &foreground);

} // namespace icons

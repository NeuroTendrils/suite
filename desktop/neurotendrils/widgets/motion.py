"""Shared Qt motion helpers for shell transitions."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import (
    QAbstractAnimation,
    QAnimationGroup,
    QByteArray,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QTimer,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget
from shiboken6 import isValid

DURATION_FAST = 180
DURATION_NORMAL = 220
DURATION_SLOW = 280

_EASING = QEasingCurve.Type.OutCubic

# Widgets carrying a motion-owned opacity effect keep the driving animation here,
# so a container fade can stop it before deleting the effect underneath it.
_EFFECT_ANIM = "_ntEffectAnim"


def _alive(widget: QWidget | None) -> bool:
    return widget is not None and isValid(widget)


def _has_live_target(anim: QAbstractAnimation) -> bool:
    """An animation outlives its target object; touching it then would warn."""
    if isinstance(anim, QPropertyAnimation):
        return anim.targetObject() is not None
    if isinstance(anim, QAnimationGroup):
        return all(
            _has_live_target(anim.animationAt(index))
            for index in range(anim.animationCount())
        )
    return True


def _stop(anim: QAbstractAnimation | None) -> None:
    if anim is None or anim.state() != QAbstractAnimation.State.Running:
        return
    if not _has_live_target(anim):
        return
    anim.stop()


def animate_width(
    widget: QWidget,
    end: int,
    *,
    duration: int = DURATION_NORMAL,
    easing: QEasingCurve.Type = _EASING,
) -> QPropertyAnimation:
    """Animate ``minimumWidth``/``maximumWidth``/``width`` toward ``end``."""
    existing = widget.property("_ntWidthAnim")
    if isinstance(existing, QPropertyAnimation):
        _stop(existing)

    start = widget.width()
    widget.setMinimumWidth(start)
    widget.setMaximumWidth(start)

    anim = QPropertyAnimation(widget, QByteArray(b"minimumWidth"), widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(easing)

    # Keep max in lockstep so the layout actually moves.
    def _sync_max(value: object) -> None:
        if isinstance(value, (int, float)):
            widget.setMaximumWidth(int(value))

    anim.valueChanged.connect(_sync_max)

    def _finish() -> None:
        widget.setMinimumWidth(end)
        widget.setMaximumWidth(end)
        widget.setFixedWidth(end)

    anim.finished.connect(_finish)
    widget.setProperty("_ntWidthAnim", anim)
    anim.start()
    return anim


def _has_effect_ancestor(widget: QWidget) -> bool:
    """Nested opacity effects make Qt paint twice into one device, so avoid them."""
    parent = widget.parentWidget()
    while parent is not None:
        if parent.graphicsEffect() is not None:
            return True
        parent = parent.parentWidget()
    return False


def _cancel_child_effects(widget: QWidget) -> None:
    """Drop in-flight child fades before fading their container."""
    for child in widget.findChildren(QWidget):
        if child.graphicsEffect() is None:
            continue
        anim = child.property(_EFFECT_ANIM)
        if isinstance(anim, QAbstractAnimation):
            _stop(anim)
        child.setGraphicsEffect(None)


def slide_stack(
    stack: QStackedWidget,
    index: int,
    *,
    forward: bool = True,
    duration: int = DURATION_NORMAL,
    distance: int = 28,
) -> None:
    """Switch pages with a short lateral slide, so direction reads as progress."""
    if index < 0 or index >= stack.count() or index == stack.currentIndex():
        return

    existing = stack.property("_ntSlide")
    if isinstance(existing, QAbstractAnimation):
        _stop(existing)

    stack.setCurrentIndex(index)
    page = stack.currentWidget()
    if page is None:
        return

    target = page.pos()
    page.move(QPoint(target.x() + (distance if forward else -distance), target.y()))

    slide = QPropertyAnimation(page, QByteArray(b"pos"), stack)
    slide.setDuration(duration)
    slide.setEndValue(target)
    slide.setEasingCurve(_EASING)

    group = QParallelAnimationGroup(stack)
    group.addAnimation(slide)

    faded = page.graphicsEffect() is None and not _has_effect_ancestor(page)
    if faded:
        _cancel_child_effects(page)
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        fade = QPropertyAnimation(effect, QByteArray(b"opacity"), stack)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(_EASING)
        group.addAnimation(fade)

    def _settle() -> None:
        page.move(target)
        if faded:
            page.setGraphicsEffect(None)

    group.finished.connect(_settle)
    stack.setProperty("_ntSlide", group)
    page.setProperty(_EFFECT_ANIM, group)
    group.start()


def stagger_in(
    widgets: Sequence[QWidget],
    *,
    duration: int = DURATION_FAST,
    gap: int = 45,
) -> None:
    """Fade widgets in one after another so lists feel like they arrive."""
    for position, widget in enumerate(widgets):
        if not _alive(widget):
            continue
        if widget.graphicsEffect() is not None or _has_effect_ancestor(widget):
            continue
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        anim = QPropertyAnimation(effect, QByteArray(b"opacity"), widget)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(_EASING)
        anim.finished.connect(
            lambda w=widget: w.setGraphicsEffect(None) if _alive(w) else None
        )
        widget.setProperty(_EFFECT_ANIM, anim)

        def _start(anim=anim, widget=widget, effect=effect) -> None:
            if not _alive(widget) or not isValid(effect):
                return
            if widget.graphicsEffect() is effect:
                anim.start()

        QTimer.singleShot(position * gap, _start)


def crossfade_stack(
    stack: QStackedWidget,
    index: int,
    *,
    duration: int = DURATION_FAST,
) -> None:
    """Fade out, switch page, fade in (QStackedWidget-safe)."""
    if index < 0 or index >= stack.count() or index == stack.currentIndex():
        return

    current = stack.currentWidget()
    if current is None:
        stack.setCurrentIndex(index)
        return

    effect = current.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        _cancel_child_effects(current)
        effect = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(effect)
    effect.setOpacity(1.0)

    half = max(60, duration // 2)
    out_anim = QPropertyAnimation(effect, QByteArray(b"opacity"), stack)
    out_anim.setDuration(half)
    out_anim.setStartValue(1.0)
    out_anim.setEndValue(0.0)
    out_anim.setEasingCurve(_EASING)

    def _swap() -> None:
        current.setGraphicsEffect(None)
        nxt = stack.widget(index)
        if nxt is None:
            stack.setCurrentIndex(index)
            return
        # Install the effect before the page is shown: work triggered by
        # showEvent can then see it and skip its own (nesting) fades.
        _cancel_child_effects(nxt)
        nxt_effect = QGraphicsOpacityEffect(nxt)
        nxt.setGraphicsEffect(nxt_effect)
        nxt_effect.setOpacity(0.0)
        stack.setCurrentIndex(index)
        in_anim = QPropertyAnimation(nxt_effect, QByteArray(b"opacity"), stack)
        in_anim.setDuration(half)
        in_anim.setStartValue(0.0)
        in_anim.setEndValue(1.0)
        in_anim.setEasingCurve(_EASING)
        # Effects are costly to keep alive; drop it once the page is opaque.
        in_anim.finished.connect(lambda: nxt.setGraphicsEffect(None))
        stack.setProperty("_ntCrossfade", in_anim)
        nxt.setProperty(_EFFECT_ANIM, in_anim)
        in_anim.start()

    existing = stack.property("_ntCrossfade")
    if isinstance(existing, QAbstractAnimation):
        _stop(existing)
    out_anim.finished.connect(_swap)
    stack.setProperty("_ntCrossfade", out_anim)
    current.setProperty(_EFFECT_ANIM, out_anim)
    out_anim.start()

"""Shared Qt motion helpers for shell transitions."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QAbstractAnimation,
    QPropertyAnimation,
    QByteArray,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget

DURATION_FAST = 180
DURATION_NORMAL = 220
DURATION_SLOW = 280

_EASING = QEasingCurve.Type.OutCubic


def _stop(anim: QAbstractAnimation | None) -> None:
    if anim is not None and anim.state() == QAbstractAnimation.State.Running:
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


def animate_opacity(
    widget: QWidget,
    end: float,
    *,
    duration: int = DURATION_FAST,
    easing: QEasingCurve.Type = _EASING,
    ensure_effect: bool = True,
) -> QPropertyAnimation | None:
    """Animate opacity via ``QGraphicsOpacityEffect``."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        if not ensure_effect:
            return None
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(1.0)
        widget.setGraphicsEffect(effect)

    existing = widget.property("_ntOpacityAnim")
    if isinstance(existing, QPropertyAnimation):
        _stop(existing)

    anim = QPropertyAnimation(effect, QByteArray(b"opacity"), widget)
    anim.setDuration(duration)
    anim.setStartValue(effect.opacity())
    anim.setEndValue(end)
    anim.setEasingCurve(easing)
    widget.setProperty("_ntOpacityAnim", anim)
    anim.start()
    return anim


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
        stack.setCurrentIndex(index)
        nxt = stack.currentWidget()
        if nxt is None:
            return
        nxt_effect = nxt.graphicsEffect()
        if not isinstance(nxt_effect, QGraphicsOpacityEffect):
            nxt_effect = QGraphicsOpacityEffect(nxt)
            nxt.setGraphicsEffect(nxt_effect)
        nxt_effect.setOpacity(0.0)
        in_anim = QPropertyAnimation(nxt_effect, QByteArray(b"opacity"), stack)
        in_anim.setDuration(half)
        in_anim.setStartValue(0.0)
        in_anim.setEndValue(1.0)
        in_anim.setEasingCurve(_EASING)
        stack.setProperty("_ntCrossfade", in_anim)
        in_anim.start()

    existing = stack.property("_ntCrossfade")
    if isinstance(existing, QAbstractAnimation):
        _stop(existing)
    out_anim.finished.connect(_swap)
    stack.setProperty("_ntCrossfade", out_anim)
    out_anim.start()

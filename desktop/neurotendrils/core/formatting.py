"""Shared display formatting helpers."""

from __future__ import annotations

import time
from datetime import datetime


def format_bytes(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024**2:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / 1024**2:.1f} MB"


def format_relative(timestamp: float, *, now: float | None = None) -> str:
    """Compact age string for list rows ("4m", "3h", "2d", or a date)."""
    if timestamp <= 0:
        return "—"
    reference = time.time() if now is None else now
    delta = max(0.0, reference - timestamp)
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 604800:
        return f"{int(delta // 86400)}d ago"
    return datetime.fromtimestamp(timestamp).strftime("%b %d, %Y")


def format_timestamp(timestamp: float) -> str:
    if timestamp <= 0:
        return "—"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

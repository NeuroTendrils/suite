"""Shared display formatting helpers."""

from __future__ import annotations


def format_bytes(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024**2:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / 1024**2:.1f} MB"

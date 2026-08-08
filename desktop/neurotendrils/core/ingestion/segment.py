"""Manual crop / segment helpers (not NeuroFlow recipe steps)."""

from __future__ import annotations

from typing import Any


def crop_raw(raw: Any, tmin: float, tmax: float) -> Any:
    """Crop continuous Raw to [tmin, tmax] seconds (inclusive end when possible)."""
    if tmax <= tmin:
        raise ValueError("tmax must be greater than tmin")
    return raw.copy().crop(tmin=float(tmin), tmax=float(tmax), include_tmax=True)

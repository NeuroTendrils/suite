"""Make values safe for json.dumps and Qt queued Signal(dict) delivery."""

from __future__ import annotations

import inspect
from typing import Any


def signal_safe(value: Any) -> Any:
    """Strip modules/classes and convert numpy so QueuedConnection can deliver."""
    if value is None or isinstance(value, (str, bool, int, float, bytes)):
        return value
    if inspect.ismodule(value) or inspect.isclass(value) or inspect.isfunction(value):
        return str(getattr(value, "__name__", None) or value)
    if isinstance(value, dict):
        return {str(k): signal_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [signal_safe(v) for v in value]
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            # Nested lists are Qt/meta-type safe; keep preview sizes modest upstream.
            if value.size > 250_000:
                return f"<array shape={tuple(value.shape)}>"
            return signal_safe(value.tolist())
        if isinstance(value, np.generic):
            return signal_safe(value.item())
    except Exception:  # noqa: BLE001
        pass
    item = getattr(value, "item", None)
    if callable(item) and not hasattr(value, "shape"):
        try:
            return signal_safe(item())
        except Exception:  # noqa: BLE001
            pass
    # Path-like
    if hasattr(value, "__fspath__"):
        try:
            return str(value)
        except Exception:  # noqa: BLE001
            pass
    return value


def json_safe(value: Any) -> Any:
    """Convert *value* to plain JSON-friendly Python types for json.dumps."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if inspect.ismodule(value) or inspect.isclass(value) or inspect.isfunction(value):
        return str(getattr(value, "__name__", None) or value)
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            if value.size > 10_000:
                return f"<array shape={tuple(value.shape)} size={int(value.size)}>"
            return json_safe(value.tolist())
        if isinstance(value, np.generic):
            return json_safe(value.item())
    except Exception:  # noqa: BLE001
        pass
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return json_safe(item())
        except Exception:  # noqa: BLE001
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            arr_size = int(getattr(value, "size", 0) or 0)
            if arr_size > 10_000:
                return f"<array size={arr_size}>"
            return json_safe(tolist())
        except Exception:  # noqa: BLE001
            pass
    if hasattr(value, "__fspath__"):
        try:
            return str(value)
        except Exception:  # noqa: BLE001
            pass
    return str(value)

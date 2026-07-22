"""Log-safe redaction for worker IPC payloads.

Never put raw EEG samples into logs. Prefer shapes and metadata.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from typing import Any

# Keys whose values are treated as sensitive sample / waveform data.
_SENSITIVE_KEYS = {
    "data",
    "samples",
    "signal",
    "signals",
    "eeg",
    "raw",
    "waveform",
    "timeseries",
    "time_series",
    "values",
    "array",
    "payload",
}

_MAX_STRING = 256
_MAX_LIST_PREVIEW = 8


def redact(value: Any, *, _key: str | None = None) -> Any:
    """Return a copy of *value* safe to write to logs."""
    if _key is not None and _key.lower() in _SENSITIVE_KEYS:
        return _summarize_sensitive(value)

    if isinstance(value, dict):
        return {str(k): redact(v, _key=str(k)) for k, v in value.items()}

    if isinstance(value, list):
        if _looks_like_numeric_series(value):
            return {
                "_redacted": "numeric_series",
                "length": len(value),
            }
        preview = [redact(item) for item in value[:_MAX_LIST_PREVIEW]]
        if len(value) > _MAX_LIST_PREVIEW:
            preview.append({"_truncated": True, "remaining": len(value) - _MAX_LIST_PREVIEW})
        return preview

    if isinstance(value, tuple):
        return redact(list(value), _key=_key)

    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"_redacted": "bytes", "length": len(value)}

    if isinstance(value, str) and len(value) > _MAX_STRING:
        return value[:_MAX_STRING] + f"...<{len(value) - _MAX_STRING} more chars>"

    return value


def _summarize_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            "_redacted": "object",
            "keys": sorted(str(k) for k in value.keys()),
        }
    if isinstance(value, (list, tuple)):
        return {
            "_redacted": "array",
            "length": len(value),
            "item_type": type(value[0]).__name__ if value else "empty",
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"_redacted": "bytes", "length": len(value)}
    if value is None:
        return {"_redacted": "null"}
    return {"_redacted": type(value).__name__}


def _looks_like_numeric_series(value: list[Any]) -> bool:
    if len(value) < 16:
        return False
    sample = value[:16]
    return all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in sample)

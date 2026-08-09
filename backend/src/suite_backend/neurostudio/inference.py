from __future__ import annotations

from typing import Any


def run_inference(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"status": "not_implemented"}


def check_compatibility(training: dict[str, Any], new_data: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if training.get("n_channels") and new_data.get("n_channels"):
        if training["n_channels"] != new_data["n_channels"]:
            issues.append("channel count mismatch")
    if training.get("sfreq") and new_data.get("sfreq"):
        if training["sfreq"] != new_data["sfreq"]:
            issues.append("sampling rate mismatch")
    return {"ok": not issues, "issues": issues}

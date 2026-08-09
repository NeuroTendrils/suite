from __future__ import annotations

from typing import Any


def export_model_bundle(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "message": "export must include model + preprocessing plan + input fingerprint",
    }

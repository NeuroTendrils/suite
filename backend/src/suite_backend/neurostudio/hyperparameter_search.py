from __future__ import annotations

from typing import Any


def search(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Internal hypertune interface. No Optuna. May not ship."""
    return {"status": "not_implemented", "message": "hyperparameter search not implemented"}

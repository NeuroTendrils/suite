from __future__ import annotations

from typing import Any


def augment_dataset(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """
    ML-team entrypoint for data augmentation.

    Must produce explicitly marked derived artifacts only.
    Never mutates raw recordings.
    """
    return {
        "status": "not_implemented",
        "message": "augmentation owned by ML team; derived-artifact contract enforced",
        "derived_artifact": None,
    }

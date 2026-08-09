from __future__ import annotations

from typing import Any

from suite_backend.domain.models import RecommendationResult, Recording


def detect_artifacts(recording: Recording, **_: Any) -> RecommendationResult:
    """Placeholder for artifact detection. Never auto-deletes; UI must confirm."""
    return RecommendationResult(
        recommendations=[],
        warnings=["artifact detection not implemented yet"],
        confidence=None,
        explanation=None,
    )

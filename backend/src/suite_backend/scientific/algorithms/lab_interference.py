from __future__ import annotations

from typing import Any

from suite_backend.domain.models import RecommendationResult, Recording


def detect_lab_interference(recording: Recording, **_: Any) -> RecommendationResult:
    """Placeholder for line noise / lab interference suggestions."""
    return RecommendationResult(
        recommendations=[],
        warnings=["lab interference detection not implemented yet"],
    )

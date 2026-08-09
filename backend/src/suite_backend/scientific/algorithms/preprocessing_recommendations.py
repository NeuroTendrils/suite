from __future__ import annotations

from typing import Any

from suite_backend.domain.models import RecommendationResult, Recording


def recommend_preprocessing(recording: Recording, **_: Any) -> RecommendationResult:
    """Placeholder for NeuroFlow preprocessing recommendations."""
    return RecommendationResult(
        recommendations=[],
        warnings=["recommendation engine not implemented yet"],
        confidence=None,
        explanation=None,
    )

from __future__ import annotations

from typing import Any

from suite_backend.domain.models import RecommendationResult, Recording
from suite_backend.neuroflow.default_plan import default_preprocessing_plan


def recommend_preprocessing(recording: Recording, **_: Any) -> RecommendationResult:
    """
    Placeholder recommender — always returns the fixed default plan.

    Not data-adaptive; same contract as NeuroStudio's EEGNet-always recommend.
    """
    del recording  # unused until a real recommender exists
    plan = default_preprocessing_plan()
    return RecommendationResult(
        recommendations=[
            {
                "kind": "preprocessing_plan",
                "plan": plan.model_dump(mode="json"),
                "placeholder": True,
                "reason": "fixed default placeholder plan (not inferred from data)",
            }
        ],
        warnings=[
            "recommendation engine not implemented — returning default_placeholder plan only",
        ],
        confidence=0.0,
        explanation="Always recommends the same filter→notch→reref placeholder plan.",
    )

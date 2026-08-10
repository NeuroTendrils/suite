"""Placeholder default NeuroFlow preprocessing plan (not a real recommender)."""

from __future__ import annotations

from suite_backend.domain.models import ProcessingPlan, ProcessingStep


def default_preprocessing_plan(*, name: str = "default_placeholder") -> ProcessingPlan:
    """
    Honest placeholder plan — fixed steps, not data-adaptive.

    Same structure every time so UI/automation can wire plans before a real recommender exists.
    """
    return ProcessingPlan(
        name=name,
        notes=(
            "PLACEHOLDER default plan — not recommended from data quality. "
            "Replace with neuroflow.recommend_preprocessing when implemented."
        ),
        steps=[
            ProcessingStep(
                operation="filter_bandpass",
                parameters={"l_freq": 1.0, "h_freq": 40.0},
                output_type="recording_artifact",
            ),
            ProcessingStep(
                operation="filter_notch",
                parameters={"freqs": [60.0]},
                output_type="recording_artifact",
            ),
            ProcessingStep(
                operation="rereference",
                parameters={"ref": "average"},
                output_type="recording_artifact",
            ),
        ],
    )

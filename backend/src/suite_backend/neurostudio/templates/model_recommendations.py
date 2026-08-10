"""Placeholder NeuroStudio model/template recommender.

Real recommendation algorithms come later. Until then, always recommend EEGNet
(Braindecode) with an explicit placeholder explanation.
"""

from __future__ import annotations

from typing import Any


def recommend_model_templates(study: Any = None, artifact: Any = None) -> dict[str, Any]:
    del study, artifact
    return {
        "recommendations": [
            {
                "template_id": "eegnet",
                "name": "EEGNet",
                "braindecode_ref": "braindecode.models.EEGNetv4",
                "reason": (
                    "Placeholder recommender: EEGNet is the default Braindecode "
                    "template until a real model-selection algorithm is implemented."
                ),
                "evidence": [
                    "Policy: always recommend EEGNet for now",
                    "Catalog includes other Braindecode models but they are not auto-selected",
                ],
                "confidence": 0.0,
                "status": "placeholder",
            }
        ],
        "warnings": [
            "model recommendation algorithm not implemented; always returning EEGNet"
        ],
        "confidence": 0.0,
        "explanation": "Placeholder: always recommend EEGNet (Braindecode).",
    }

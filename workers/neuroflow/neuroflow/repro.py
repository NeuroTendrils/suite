"""Reproducibility metadata for NeuroFlow runs.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from . import __version__

# Fixed seed used by stochastic steps (ICA). Keep in sync with suite PlanIo stamps.
ICA_RANDOM_STATE = 42


def environment_versions() -> dict[str, Any]:
    """Return JSON-serializable library / runtime versions (no paths with secrets)."""
    versions: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "neuroflow": __version__,
        "ica_random_state": ICA_RANDOM_STATE,
    }

    try:
        import mne

        versions["mne"] = getattr(mne, "__version__", "unknown")
    except ImportError:
        versions["mne"] = None

    try:
        import numpy as np

        versions["numpy"] = getattr(np, "__version__", "unknown")
    except ImportError:
        versions["numpy"] = None

    try:
        import sklearn

        versions["sklearn"] = getattr(sklearn, "__version__", "unknown")
    except ImportError:
        versions["sklearn"] = None

    try:
        import scipy

        versions["scipy"] = getattr(scipy, "__version__", "unknown")
    except ImportError:
        versions["scipy"] = None

    return versions


def run_reproducibility(plan: dict[str, Any], steps_applied: list[dict[str, Any]]) -> dict[str, Any]:
    """Bundle versions + plan params so a run can be audited / re-executed."""
    return {
        "schema": 1,
        "seed": ICA_RANDOM_STATE,
        "ica_random_state": ICA_RANDOM_STATE,
        "environment": environment_versions(),
        "plan": {
            "v": plan.get("v", 1),
            "steps": [
                {"step_id": s.get("step_id"), "params": dict(s.get("params") or {})}
                for s in (plan.get("steps") or [])
                if isinstance(s, dict)
            ],
        },
        "steps_applied": steps_applied,
    }

"""Run predictions with a model trained by `run.py`.

Train + save a model first:

    python run.py

Then feed data through it and print the predictions:

    python predict.py

By default it predicts on config.DATA_PATH using config.MODEL_OUT.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import os
import sys

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from neurostudio.preprocessing import run_prediction  # noqa: E402
from neurostudio.train import TrainError  # noqa: E402


def main() -> int:
    try:
        run_prediction()
    except TrainError as exc:
        print(f"[{exc.code}] {exc.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

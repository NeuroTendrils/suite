"""Convenience launcher for the preprocess-and-train pipeline.

From inside this folder, just run:

    python run.py

It prints the full training report to the console. (Equivalent to
`python -m neurostudio.preprocessing` from the parent folder.)

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import os
import sys

# Allow running this file directly (python run.py) from any working directory:
# put the folder that CONTAINS the neurostudio package on sys.path so the
# package's relative imports resolve.
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from neurostudio.preprocessing import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

"""Resolve import paths for dev checkout vs PyInstaller bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def bundle_dir() -> Path:
    """PyInstaller extraction / onedir package root."""
    return Path(sys._MEIPASS)  # type: ignore[attr-defined]


def repo_root() -> Path:
    """Suite repo root when running from source."""
    return Path(__file__).resolve().parents[2]


def ensure_sys_path() -> None:
    """Make neuroflow / neurostudio / desktop importable."""
    if is_frozen():
        root = bundle_dir()
        candidates = [
            root,
            root / "workers" / "neuroflow",
            root / "workers" / "neurostudio",
        ]
    else:
        root = repo_root()
        candidates = [
            root / "desktop",
            root / "workers" / "neuroflow",
            root / "workers" / "neurostudio",
        ]

    for path in candidates:
        text = str(path)
        if path.exists() and text not in sys.path:
            sys.path.insert(0, text)

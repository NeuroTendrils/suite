"""Device selection helpers for NeuroStudio training.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from typing import Any


def list_devices() -> list[dict[str, Any]]:
    """Return available train devices with human labels."""
    devices: list[dict[str, Any]] = [{"id": "cpu", "label": "CPU", "available": True}]

    try:
        import torch
    except ImportError:
        return devices

    cuda_ok = bool(torch.cuda.is_available())
    devices.append({"id": "cuda", "label": "CUDA (NVIDIA GPU)", "available": cuda_ok})

    mps_ok = False
    if hasattr(torch.backends, "mps"):
        try:
            mps_ok = bool(torch.backends.mps.is_available())
        except Exception:  # noqa: BLE001
            mps_ok = False
    devices.append({"id": "mps", "label": "MPS (Apple Silicon)", "available": mps_ok})
    return devices


def resolve_device(requested: str | None) -> str:
    """Map a requested device id to a torch device string."""
    import torch

    req = (requested or "cpu").strip().lower()
    if req in {"", "auto"}:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if req == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA requested but not available")
        return "cuda"
    if req == "mps":
        if not (hasattr(torch.backends, "mps") and torch.backends.mps.is_available()):
            raise ValueError("MPS requested but not available")
        return "mps"
    if req == "cpu":
        return "cpu"
    raise ValueError(f"Unknown device: {requested}")

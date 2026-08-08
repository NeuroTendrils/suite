"""Auxiliary stream helpers (EMG, gyro, …) — schema + light validation for P0."""

from __future__ import annotations

from pathlib import Path

from neurotendrils.core.ingestion.schema import AuxStream


def validate_aux_paths(streams: list[AuxStream], *, project_root: str | Path | None = None) -> list[str]:
    """Return human-readable warnings for missing aux files (non-fatal)."""
    warnings: list[str] = []
    root = Path(project_root).expanduser() if project_root else None
    for stream in streams:
        path = Path(stream.path).expanduser()
        if not path.is_file() and root is not None:
            candidate = (root / stream.path).resolve()
            if candidate.is_file():
                continue
        if not path.is_file():
            warnings.append(f"aux “{stream.kind}” missing: {stream.path}")
    return warnings

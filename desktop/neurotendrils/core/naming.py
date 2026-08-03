"""Shared basename sanitization for plans, runs, trains, and exports."""

from __future__ import annotations

from pathlib import Path


def sanitize_base_name(name: str, fallback: str = "item") -> str:
    text = (name or "").strip()
    if not text:
        return fallback
    chars: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"_", "-"}:
            chars.append(ch)
        else:
            chars.append("_")
    cleaned = "".join(chars).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or fallback


def unique_path(directory: Path, stem: str, suffix: str) -> Path:
    """Return directory/stem+suffix, appending _1, _2, … on collision."""
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{suffix}"
    index = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def unique_dir(directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / stem
    index = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{index}"
        index += 1
    return candidate

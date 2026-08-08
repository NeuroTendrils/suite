"""Apply standard or custom montages to Raw (manual prep helper)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neurotendrils.core.ingestion.schema import MontageConfig


class MontageError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


STANDARD_MONTAGES: tuple[str, ...] = (
    "standard_1005",
    "standard_1020",
    "standard_alphabetic",
    "standard_post_auricular_mastoid",
    "biosemi16",
    "biosemi32",
    "biosemi64",
    "easycap-M1",
    "easycap-M10",
    "EGI_256",
    "GSN-HydroCel-32",
    "GSN-HydroCel-64_1.0",
    "GSN-HydroCel-128",
    "GSN-HydroCel-256",
    "mgh60",
    "mgh70",
)


def apply_montage(raw: Any, config: MontageConfig) -> Any:
    """Set montage on *raw* from config; returns the same object."""
    import mne

    if config.custom_path:
        path = Path(config.custom_path).expanduser()
        if not path.is_file():
            raise MontageError(f"custom montage not found: {path}")
        montage = mne.channels.read_custom_montage(str(path))
        raw.set_montage(montage, on_missing="warn", verbose="ERROR")
        return raw

    if config.name:
        try:
            montage = mne.channels.make_standard_montage(config.name)
        except Exception as exc:  # noqa: BLE001
            raise MontageError(f"unknown standard montage “{config.name}”: {exc}") from exc
        raw.set_montage(montage, on_missing="warn", verbose="ERROR")
        return raw

    return raw

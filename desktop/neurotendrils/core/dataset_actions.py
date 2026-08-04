"""Project-wide helpers to create multi-file lab datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import QFileDialog, QWidget

from neurotendrils.core.eeg_formats import lab_dataset_file_filter
from neurotendrils.core.jobs import create_dataset_job, start_bound_job
from neurotendrils.core.library import notify_library_changed
from neurotendrils.core.notifications import notify
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.widgets.modals import alert, prompt_text

OkCb = Callable[[dict[str, Any]], None]
FailCb = Callable[[str, str], None]


def prompt_and_create_dataset(
    anchor: QWidget,
    holder: Any,
    *,
    on_ok: OkCb | None = None,
    on_fail: FailCb | None = None,
    after: Callable[[], None] | None = None,
    job_attr: str = "_job",
) -> bool:
    """Show file/name/sfreq prompts and start a create_dataset job on *holder*.

    Returns False if the user cancelled or a job is already running.
    """
    project = ProjectDir.instance()
    if not project.root:
        alert(anchor, "Project required", "Open a project first.")
        return False
    if getattr(holder, job_attr, None) is not None and getattr(
        getattr(holder, job_attr), "is_running", lambda: False
    )():
        alert(anchor, "Busy", "Wait for the current job to finish.")
        return False

    start = project.datasets_dir()
    if not start.is_dir():
        start = Path.home()
    paths, _ = QFileDialog.getOpenFileNames(
        anchor,
        "Select lab EEG sources",
        str(start),
        lab_dataset_file_filter(),
    )
    if not paths:
        return False

    default_name = Path(paths[0]).stem
    name, ok = prompt_text(anchor, "Dataset name", "Name", default_name)
    if not ok or not name.strip():
        return False

    sfreq_text, ok = prompt_text(
        anchor,
        "Sampling rate",
        "Sampling rate (Hz) for headerless .txt (used when the file has no sfreq)",
        "500",
    )
    if not ok:
        return False
    try:
        sfreq = float(sfreq_text)
        if sfreq <= 0:
            raise ValueError
    except ValueError:
        alert(anchor, "Invalid rate", "Enter a positive sampling rate in Hz.")
        return False

    def _ok(result: dict[str, Any]) -> None:
        notify_library_changed()
        warnings = result.get("warnings") or []
        title = str(result.get("name") or "Dataset")
        n = int(result.get("n_members") or 0)
        notify(
            "Dataset created",
            f"{title} · {n} files",
            level="success",
        )
        if warnings:
            alert(
                anchor,
                "Dataset imported",
                "Imported with warnings:\n- "
                + "\n- ".join(str(w) for w in warnings[:8]),
            )
        if on_ok is not None:
            on_ok(result)

    def _fail(code: str, message: str) -> None:
        alert(anchor, "Dataset import failed", message)
        if on_fail is not None:
            on_fail(code, message)

    job = create_dataset_job(sources=paths, name=name.strip(), sfreq=sfreq)
    start_bound_job(holder, job_attr, job, _ok, _fail, after)
    return True

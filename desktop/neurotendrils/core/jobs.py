"""Background jobs: call NeuroFlow / NeuroStudio in-process"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from neurotendrils.core.projectdir import ProjectDir


class WorkerJob(QObject):
    progress = Signal(dict)
    finished = Signal(dict)
    failed = Signal(str, str)  # code, message

    def __init__(self, fn: Callable[[], dict[str, Any]], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._thread = QThread(parent)
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)

    def start(self) -> None:
        self._thread.start()

    def request_interruption(self) -> None:
        self._thread.requestInterruption()

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def _run(self) -> None:
        try:
            result = self._fn()
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 — surface to UI
            code = getattr(exc, "code", type(exc).__name__)
            message = getattr(exc, "message", str(exc))
            self.failed.emit(str(code), str(message))
        finally:
            self._thread.quit()


def _assert_in_project(*paths: str | None) -> None:
    project = ProjectDir.instance()
    for path in paths:
        if path:
            project.require_contains(path)


def fingerprint_job(path: str) -> WorkerJob:
    _assert_in_project(path)

    def work() -> dict[str, Any]:
        from neuroflow.fingerprint import fingerprint_file

        return fingerprint_file(path)

    return WorkerJob(work)


def run_plan_job(input_path: str, output_path: str, plan: dict[str, Any]) -> WorkerJob:
    _assert_in_project(input_path, output_path)
    job = WorkerJob(lambda: {})

    def work() -> dict[str, Any]:
        from neuroflow.run import run_plan

        return run_plan(
            input_path,
            output_path,
            plan,
            on_progress=lambda payload: job.progress.emit(payload),
        )

    job._fn = work  # noqa: SLF001
    return job


def train_job(
    *,
    input_path: str,
    output_dir: str,
    template_id: str,
    config: dict[str, Any],
    device: str,
) -> WorkerJob:
    _assert_in_project(input_path, output_dir)
    job = WorkerJob(lambda: {})

    def work() -> dict[str, Any]:
        from neurostudio.train import train

        return train(
            input_path=input_path,
            output_dir=output_dir,
            template_id=template_id,
            config=config,
            device=device,
            on_progress=lambda payload: job.progress.emit(payload),
        )

    job._fn = work  # noqa: SLF001
    return job


def export_job(
    *,
    checkpoint_path: str,
    output_dir: str,
    format: str,
    train_meta_path: str | None,
) -> WorkerJob:
    _assert_in_project(checkpoint_path, output_dir, train_meta_path)
    job = WorkerJob(lambda: {})

    def work() -> dict[str, Any]:
        from neurostudio.export import export_model

        return export_model(
            checkpoint_path=checkpoint_path,
            output_dir=output_dir,
            format=format,
            train_meta_path=train_meta_path,
            on_progress=lambda payload: job.progress.emit(payload),
        )

    job._fn = work  # noqa: SLF001
    return job

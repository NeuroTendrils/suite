"""Background jobs: call NeuroFlow / NeuroStudio in-process"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal

from neurotendrils.core.projectdir import ProjectDir


class WorkerJob(QObject):
    progress = Signal(dict)
    finished = Signal(dict)
    failed = Signal(str, str)  # code, message

    def __init__(
        self,
        fn: Callable[[], dict[str, Any]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._fn = fn
        self._cancelled = False
        self._thread = QThread(parent)
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)

    def set_work(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._fn = fn

    def start(self) -> None:
        self._thread.start()

    def request_interruption(self) -> None:
        self._cancelled = True
        self._thread.requestInterruption()

    def is_cancelled(self) -> bool:
        return self._cancelled or self._thread.isInterruptionRequested()

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def request_cancel(self) -> None:
        """Ask the worker to stop; does not block the UI thread."""
        self.request_interruption()
        self._thread.quit()

    def _run(self) -> None:
        try:
            if self._fn is None:
                raise RuntimeError("WorkerJob has no work function")
            if self.is_cancelled():
                self.failed.emit("cancelled", "Cancelled")
                return
            result = self._fn()
            if self.is_cancelled():
                self.failed.emit("cancelled", "Cancelled")
                return
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 — surface to UI
            code = getattr(exc, "code", type(exc).__name__)
            message = getattr(exc, "message", str(exc))
            if self.is_cancelled() or str(code) == "cancelled":
                self.failed.emit("cancelled", "Cancelled")
            else:
                self.failed.emit(str(code), str(message))
        finally:
            self._thread.quit()


def start_bound_job(
    holder: Any,
    attr: str,
    job: WorkerJob,
    on_ok: Callable[[dict[str, Any]], None],
    on_fail: Callable[[str, str], None],
    after: Callable[[], None] | None = None,
) -> int:
    """Store job on holder.attr with a generation token so stale callbacks are ignored."""

    token = int(getattr(holder, "_job_token", 0)) + 1
    setattr(holder, "_job_token", token)
    setattr(holder, attr, job)

    def ok(result: dict[str, Any]) -> None:
        if getattr(holder, "_job_token", None) != token:
            return
        setattr(holder, attr, None)
        on_ok(result)
        if after is not None:
            after()

    def fail(code: str, message: str) -> None:
        if getattr(holder, "_job_token", None) != token:
            return
        setattr(holder, attr, None)
        on_fail(code, message)
        if after is not None:
            after()

    job.finished.connect(ok)
    job.failed.connect(fail)
    job.start()
    if after is not None:
        after()
    return token


def cancel_bound_job(holder: Any, attr: str = "_job") -> bool:
    """Invalidate callbacks and request cancel without blocking the UI."""
    job: WorkerJob | None = getattr(holder, attr, None)
    setattr(holder, "_job_token", int(getattr(holder, "_job_token", 0)) + 1)
    setattr(holder, attr, None)
    if job is None:
        return False
    for signal in (job.finished, job.failed, job.progress):
        try:
            signal.disconnect()
        except (RuntimeError, TypeError):
            pass
    job.request_cancel()
    return True


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


def import_recording_job(source_path: str) -> WorkerJob:
    def work() -> dict[str, Any]:
        from neurotendrils.core.dataset_io import import_recording

        dest, copied = import_recording(source_path)
        return {"path": dest, "copied": copied}

    return WorkerJob(work)


def run_plan_job(
    input_path: str,
    output_path: str,
    plan: dict[str, Any],
    *,
    meta_path: str | None = None,
) -> WorkerJob:
    _assert_in_project(input_path, output_path, meta_path)
    job = WorkerJob()
    plan_snapshot = deepcopy(plan)

    def work() -> dict[str, Any]:
        from neuroflow.run import run_plan

        from neurotendrils.core.plans import write_run_metadata

        ProjectDir.instance().require_contains(input_path, "input")
        ProjectDir.instance().require_contains(output_path, "output")
        result = run_plan(
            input_path,
            output_path,
            plan_snapshot,
            on_progress=lambda payload: job.progress.emit(payload),
            should_cancel=job.is_cancelled,
        )
        out = str(result.get("output_path") or output_path)
        ProjectDir.instance().require_contains(out, "output")
        if meta_path:
            write_run_metadata(
                Path(meta_path),
                input_path=input_path,
                output_path=out,
                plan=plan_snapshot,
                result=result,
            )
            result["meta_path"] = meta_path
        return result

    job.set_work(work)
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
    job = WorkerJob()

    def work() -> dict[str, Any]:
        from neurostudio.train import train

        ProjectDir.instance().require_contains(input_path, "input")
        ProjectDir.instance().require_contains(output_dir, "output")
        return train(
            input_path=input_path,
            output_dir=output_dir,
            template_id=template_id,
            config=config,
            device=device,
            on_progress=lambda payload: job.progress.emit(payload),
            should_cancel=job.is_cancelled,
            allow_synthetic=False,
        )

    job.set_work(work)
    return job


def export_job(
    *,
    checkpoint_path: str,
    output_dir: str,
    format: str,
    train_meta_path: str | None,
) -> WorkerJob:
    _assert_in_project(checkpoint_path, output_dir, train_meta_path)
    job = WorkerJob()

    def work() -> dict[str, Any]:
        from neurostudio.export import export_model

        ProjectDir.instance().require_contains(checkpoint_path, "checkpoint")
        ProjectDir.instance().require_contains(output_dir, "output")
        return export_model(
            checkpoint_path=checkpoint_path,
            output_dir=output_dir,
            format=format,
            train_meta_path=train_meta_path,
            on_progress=lambda payload: job.progress.emit(payload),
        )

    job.set_work(work)
    return job

"""Background jobs: call NeuroFlow / NeuroStudio in-process."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from neurotendrils.core.jsonutil import json_safe, signal_safe
from neurotendrils.core.projectdir import ProjectDir


class _Runner(QObject):
    """Lives on the worker thread; does the actual work."""

    finished = Signal(dict)
    failed = Signal(str, str)

    def __init__(self, fn: Callable[[], dict[str, Any]], owner: "WorkerJob") -> None:
        super().__init__()
        self._fn = fn
        self._owner = owner

    @Slot()
    def run(self) -> None:
        try:
            if self._owner.is_cancelled():
                self.failed.emit("cancelled", "Cancelled")
                return
            result = self._fn()
            if self._owner.is_cancelled():
                self.failed.emit("cancelled", "Cancelled")
                return
            # Strip modules/classes before queued cross-thread delivery.
            if not isinstance(result, dict):
                raise TypeError(f"job must return dict, got {type(result).__name__}")
            self.finished.emit(signal_safe(result))
        except Exception as exc:  # noqa: BLE001 — surface to UI
            code = getattr(exc, "code", type(exc).__name__)
            message = getattr(exc, "message", str(exc))
            if self._owner.is_cancelled() or str(code) == "cancelled":
                self.failed.emit("cancelled", "Cancelled")
            else:
                self.failed.emit(str(code), str(message))


class WorkerJob(QObject):
    """GUI-thread facade: owns the QThread and forwards worker signals."""

    progress = Signal(dict)
    finished = Signal(dict)
    failed = Signal(str, str)
    thread_finished = Signal()

    def __init__(
        self,
        fn: Callable[[], dict[str, Any]] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._fn = fn or (lambda: {})
        self._cancelled = False
        self._thread = QThread(self)
        self._runner: _Runner | None = None
        self._thread.finished.connect(self.thread_finished.emit)

    def set_work(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._fn = fn

    def start(self) -> None:
        if self._thread.isRunning():
            return
        self._runner = _Runner(self._fn, self)
        self._runner.moveToThread(self._thread)
        self._thread.started.connect(self._runner.run)
        # Forward to this (GUI-thread) object with a queued connection.
        self._runner.finished.connect(self.finished.emit, Qt.ConnectionType.QueuedConnection)
        self._runner.failed.connect(self.failed.emit, Qt.ConnectionType.QueuedConnection)
        self._runner.finished.connect(self._thread.quit)
        self._runner.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._runner.deleteLater)
        self._thread.start()

    def request_interruption(self) -> None:
        self._cancelled = True
        self._thread.requestInterruption()

    def is_cancelled(self) -> bool:
        return self._cancelled or self._thread.isInterruptionRequested()

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def request_cancel(self) -> None:
        self.request_interruption()
        self._thread.quit()


def start_bound_job(
    holder: Any,
    attr: str,
    job: WorkerJob,
    on_ok: Callable[[dict[str, Any]], None],
    on_fail: Callable[[str, str], None],
    after: Callable[[], None] | None = None,
) -> int:
    """Store job on holder.attr; keep it alive until its QThread finishes."""

    token = int(getattr(holder, "_job_token", 0)) + 1
    setattr(holder, "_job_token", token)
    setattr(holder, attr, job)

    alive: list[WorkerJob] = getattr(holder, "_alive_jobs", None)  # type: ignore[assignment]
    if alive is None:
        alive = []
        setattr(holder, "_alive_jobs", alive)
    alive.append(job)

    def _release() -> None:
        try:
            alive.remove(job)
        except ValueError:
            pass

    job.thread_finished.connect(_release)

    def ok(result: dict[str, Any]) -> None:
        if getattr(holder, "_job_token", None) != token:
            return
        if getattr(holder, attr, None) is job:
            setattr(holder, attr, None)
        on_ok(result)
        if after is not None:
            after()

    def fail(code: str, message: str) -> None:
        if getattr(holder, "_job_token", None) != token:
            return
        if getattr(holder, attr, None) is job:
            setattr(holder, attr, None)
        on_fail(code, message)
        if after is not None:
            after()

    # WorkerJob lives on the GUI thread, so these are direct/GUI-safe.
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
    root = ProjectDir.instance().root

    def work() -> dict[str, Any]:
        from neurotendrils.core.dataset_io import import_recording

        dest, copied = import_recording(source_path, project_root=root)
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
    root = ProjectDir.instance().root

    def work() -> dict[str, Any]:
        from neuroflow.run import run_plan

        from neurotendrils.core.plans import write_run_metadata
        from neurotendrils.core.projectdir import resolve_path

        def _inside(path: str | Path, label: str) -> Path:
            resolved = resolve_path(path)
            root_resolved = resolve_path(root)
            try:
                resolved.relative_to(root_resolved)
            except ValueError as exc:
                if resolved != root_resolved:
                    raise PermissionError(
                        f"{label} must be inside the project folder"
                    ) from exc
            return resolved

        _inside(input_path, "input")
        _inside(output_path, "output")
        result = run_plan(
            input_path,
            output_path,
            plan_snapshot,
            on_progress=lambda payload: job.progress.emit(signal_safe(payload)),
            should_cancel=job.is_cancelled,
        )
        result = json_safe(result)
        out = str(result.get("output_path") or output_path)
        _inside(out, "output")
        if meta_path:
            write_run_metadata(
                Path(meta_path),
                input_path=input_path,
                output_path=out,
                plan=plan_snapshot,
                result=result,
                project_root=root,
            )
            result["meta_path"] = meta_path
        return result

    job.set_work(work)
    return job


def preview_recording_job(
    path: str, *, max_sec: float = 30.0, max_ch: int = 16
) -> WorkerJob:
    """Load a short, decimated preview for the EEG viewer (off the GUI thread)."""
    _assert_in_project(path)
    job = WorkerJob()

    def work() -> dict[str, Any]:
        import numpy as np

        from neurotendrils.core.ingestion.readers import read_recording

        raw = read_recording(path, preload=True)
        import mne

        events: list[dict[str, Any]] = []
        if isinstance(raw, mne.Epochs):
            data = raw.get_data()
            data = data[: min(8, len(data))]
            flat = data.transpose(1, 0, 2).reshape(data.shape[1], -1)
            sfreq = float(raw.info["sfreq"])
            ch_names = list(raw.ch_names)[:max_ch]
            flat = flat[:max_ch]
            decim = max(1, int(round(sfreq / 100.0)))
            preview = flat[:, ::decim]
            # Nested lists — QueuedConnection cannot reliably deliver ndarray.
        return {
                "data": preview.astype(np.float32).tolist(),
                "sfreq": sfreq / decim,
                "ch_names": ch_names,
                "events": events,
                "duration_sec": float(preview.shape[1] / (sfreq / decim)),
                "all_ch_names": list(raw.ch_names),
            }

        picks = mne.pick_types(raw.info, eeg=True, eog=True, meg=False, exclude=[])
        if len(picks) == 0:
            picks = np.arange(min(max_ch, len(raw.ch_names)))
        picks = picks[:max_ch]
        sfreq = float(raw.info["sfreq"])
        n_max = int(sfreq * max_sec)
        data = raw.get_data(picks=picks, start=0, stop=min(n_max, raw.n_times))
        decim = max(1, int(round(sfreq / 100.0)))
        preview = data[:, ::decim]
        ann = getattr(raw, "annotations", None)
        if ann is not None:
            for onset, duration, desc in zip(ann.onset, ann.duration, ann.description):
                if float(onset) > max_sec:
                    break
                events.append(
                    {
                        "onset": float(onset),
                        "duration": float(duration),
                        "label": str(desc),
                        "kind": (
                            "bad" if str(desc).upper().startswith("BAD") else "event"
                        ),
                    }
                )
        return {
            "data": preview.astype(np.float32).tolist(),
            "sfreq": sfreq / decim,
            "ch_names": [raw.ch_names[i] for i in picks],
            "events": events,
            "duration_sec": float(preview.shape[1] / (sfreq / decim)),
            "all_ch_names": list(raw.ch_names),
            "bads": list(raw.info.get("bads") or []),
        }

    job.set_work(work)
    return job


def review_qa_job(path: str) -> WorkerJob:
    """ICA summary + ERP + augment preview off the GUI thread."""
    _assert_in_project(path)
    job = WorkerJob()

    def work() -> dict[str, Any]:
        from neuroflow.qa import (
            augment_preview_pairs,
            erp_averages,
            ica_component_summary,
        )

        p = Path(path)
        out: dict[str, Any] = {
            "path": str(p),
            "ica": None,
            "erp": None,
            "augment": None,
        }
        epo = p
        continuous = p
        # Prefer artifacts next to the run output (ica_summary.json) — no refit.
        summary_candidates = [p.parent / "ica_summary.json"]
        for cand in summary_candidates:
            if cand.is_file():
                try:
                    out["ica"] = ica_component_summary(str(p))
                    break
                except Exception as exc:  # noqa: BLE001
                    out["ica_error"] = str(exc)

        if p.is_file() and "-epo" not in p.name.lower():
            sibling = p.parent / "cleaned-epo.fif"
            if sibling.is_file():
                epo = sibling
            if out["ica"] is None:
                try:
                    out["ica"] = ica_component_summary(str(continuous))
                except Exception as exc:  # noqa: BLE001
                    out["ica_error"] = str(exc)
            if epo == p and out.get("erp") is None:
                # Continuous-only run: still try ERP if somehow epoched later.
                pass
        elif p.is_file():
            raw_guess = p.with_name(p.name.replace("-epo.fif", ".fif"))
            if "cleaned-epo" in p.name:
                raw_guess = p.with_name("cleaned.fif")
            if raw_guess.is_file():
                continuous = raw_guess
            if out["ica"] is None:
                try:
                    out["ica"] = ica_component_summary(str(continuous))
                except Exception as exc:  # noqa: BLE001
                    out["ica_error"] = str(exc)

        if epo.is_file() and ("-epo" in epo.name.lower() or epo != continuous):
            try:
                out["erp"] = erp_averages(str(epo))
            except Exception as exc:  # noqa: BLE001
                out["erp_error"] = str(exc)
            try:
                out["augment"] = augment_preview_pairs(str(epo))
            except Exception as exc:  # noqa: BLE001
                out["augment_error"] = str(exc)
        return out

    job.set_work(work)
    return job


def persist_bad_spans_job(path: str, spans: list[dict[str, Any]]) -> WorkerJob:
    """Write BAD annotations onto a FIF recording."""
    _assert_in_project(path)
    job = WorkerJob()

    def work() -> dict[str, Any]:
        import mne

        from neurotendrils.core.ingestion.readers import read_recording

        raw = read_recording(path, preload=True)
        if isinstance(raw, mne.Epochs):
            raise RuntimeError("Cannot paint BAD spans on epoched data")
        onsets = list(raw.annotations.onset) if raw.annotations else []
        durations = list(raw.annotations.duration) if raw.annotations else []
        descs = list(raw.annotations.description) if raw.annotations else []
        for span in spans:
            onsets.append(float(span["onset"]))
            durations.append(float(span["duration"]))
            descs.append("BAD")
        raw.set_annotations(mne.Annotations(onsets, durations, descs))
        out = path
        if not str(path).lower().endswith((".fif", ".fif.gz")):
            out = str(Path(path).with_suffix(".fif"))
        raw.save(out, overwrite=True, verbose="ERROR")
        return {"path": out, "n_bad": len(spans)}

    job.set_work(work)
    return job


def apply_montage_job(path: str, montage_name: str) -> WorkerJob:
    """Apply a standard montage and save back to FIF."""
    _assert_in_project(path)
    job = WorkerJob()

    def work() -> dict[str, Any]:
        import mne

        from neurotendrils.core.ingestion.montage import apply_montage
        from neurotendrils.core.ingestion.readers import read_recording
        from neurotendrils.core.ingestion.schema import MontageConfig

        raw = read_recording(path, preload=True)
        if isinstance(raw, mne.Epochs):
            raise RuntimeError("Montage apply expects continuous Raw")
        apply_montage(raw, MontageConfig(name=montage_name))
        out = path
        if not str(path).lower().endswith((".fif", ".fif.gz")):
            out = str(Path(path).with_suffix(".fif"))
        raw.save(out, overwrite=True, verbose="ERROR")
        return {"path": out, "montage": montage_name}

    job.set_work(work)
    return job


def drop_channels_job(path: str, channel_names: list[str]) -> WorkerJob:
    """Mark channels as bad and drop them from the saved FIF."""
    _assert_in_project(path)
    job = WorkerJob()

    def work() -> dict[str, Any]:
        import mne

        from neurotendrils.core.ingestion.readers import read_recording

        raw = read_recording(path, preload=True)
        if isinstance(raw, mne.Epochs):
            raise RuntimeError("Channel drop expects continuous Raw")
        names = [n for n in channel_names if n in raw.ch_names]
        if not names:
            return {"path": path, "dropped": []}
        raw.drop_channels(names)
        out = path
        if not str(path).lower().endswith((".fif", ".fif.gz")):
            out = str(Path(path).with_suffix(".fif"))
        raw.save(out, overwrite=True, verbose="ERROR")
        return {"path": out, "dropped": names}

    job.set_work(work)
    return job


def train_job(
    *,
    input_path: str = "",
    output_dir: str,
    template_id: str,
    config: dict[str, Any],
    device: str,
    dataset_path: str | None = None,
) -> WorkerJob:
    paths = [output_dir]
    if dataset_path:
        paths.append(dataset_path)
    if input_path:
        paths.append(input_path)
    _assert_in_project(*paths)
    job = WorkerJob()
    root = ProjectDir.instance().root

    def work() -> dict[str, Any]:
        from neurostudio.train import train

        from neurotendrils.core.projectdir import resolve_path

        def _inside(path: str) -> None:
            resolved = resolve_path(path)
            root_resolved = resolve_path(root)
            try:
                resolved.relative_to(root_resolved)
            except ValueError as exc:
                if resolved != root_resolved:
                    raise PermissionError(
                        "path must be inside the project folder"
                    ) from exc

        if dataset_path:
            _inside(dataset_path)
        if input_path:
            _inside(input_path)
        _inside(output_dir)
        return train(
            input_path=input_path or "",
            dataset_path=dataset_path,
            output_dir=output_dir,
            template_id=template_id,
            config=config,
            device=device,
            on_progress=lambda payload: job.progress.emit(signal_safe(payload)),
            should_cancel=job.is_cancelled,
            allow_synthetic=False,
        )

    job.set_work(work)
    return job


def run_dataset_plan_job(
    *,
    dataset_path: str,
    plan: dict[str, Any],
) -> WorkerJob:
    """Clean every member of a dataset manifest with a NeuroFlow plan."""
    _assert_in_project(dataset_path)
    job = WorkerJob()
    root = ProjectDir.instance().root
    plan_snapshot = deepcopy(plan)

    def work() -> dict[str, Any]:
        from neurotendrils.core.dataset_clean import (
            DatasetCleanError,
            clean_dataset_with_plan,
        )

        try:
            return clean_dataset_with_plan(
                dataset_path,
                plan_snapshot,
                project_root=root,
                on_progress=lambda payload: job.progress.emit(signal_safe(payload)),
                should_cancel=job.is_cancelled,
            )
        except DatasetCleanError as exc:
            raise RuntimeError(exc.message) from exc

    job.set_work(work)
    return job


def create_dataset_job(
    *,
    sources: list[str],
    name: str,
    sfreq: float = 500.0,
) -> WorkerJob:
    job = WorkerJob()
    root = ProjectDir.instance().root

    def work() -> dict[str, Any]:
        from neurotendrils.core.lab_ingest import IngestError, create_dataset_from_sources

        try:
            manifest_path, manifest = create_dataset_from_sources(
                sources,
                name=name,
                sfreq=sfreq,
                project_root=root,
                on_progress=lambda payload: job.progress.emit(signal_safe(payload)),
            )
        except IngestError as exc:
            raise RuntimeError(exc.message) from exc
        return {
            "manifest_path": manifest_path,
            "name": manifest.name,
            "n_members": len(manifest.members),
            "warnings": list(manifest.meta.get("warnings") or []),
            "class_names": list(manifest.label.class_names),
        }

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

        return export_model(
            checkpoint_path=checkpoint_path,
            output_dir=output_dir,
            format=format,
            train_meta_path=train_meta_path,
            on_progress=lambda payload: job.progress.emit(signal_safe(payload)),
        )

    job.set_work(work)
    return job


def infer_job(
    *,
    checkpoint_path: str,
    output_dir: str,
    input_path: str = "",
    dataset_path: str | None = None,
    device: str = "cpu",
) -> WorkerJob:
    paths = [checkpoint_path, output_dir]
    if input_path:
        paths.append(input_path)
    if dataset_path:
        paths.append(dataset_path)
    _assert_in_project(*paths)
    job = WorkerJob()

    def work() -> dict[str, Any]:
        from neurostudio.predict import PredictError, predict

        try:
            return predict(
                checkpoint_path=checkpoint_path,
                input_path=input_path,
                dataset_path=dataset_path,
                output_dir=output_dir,
                device=device,
                on_progress=lambda payload: job.progress.emit(signal_safe(payload)),
            )
        except PredictError as exc:
            raise RuntimeError(exc.message) from exc

    job.set_work(work)
    return job

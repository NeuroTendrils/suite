"""NeuroFlow page: import → fingerprint → plan → run (in-process workers)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from neurotendrils.core.eeg_formats import (
    extension_badge,
    import_file_filter,
    import_format_hint,
)
from neurotendrils.core.formatting import format_bytes
from neurotendrils.core.jobs import (
    WorkerJob,
    cancel_bound_job,
    fingerprint_job,
    import_recording_job,
    run_plan_job,
    start_bound_job,
)
from neurotendrils.core.plans import (
    default_params,
    find_step,
    from_fingerprint,
    load_plan,
    make_step,
    save_plan,
    step_catalog,
    suggest_run_paths,
    validate_plan,
    validate_step_params,
)
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.widgets.layoututil import clear_layout
from neurotendrils.widgets.pageheader import PageHeader
from neurotendrils.widgets.schema_form import SchemaEditDialog
from neurotendrils.widgets.scroll_page import ScrollPage
from neurotendrils.widgets.skeleton import SkeletonLoader


def _summarize_params(params: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in params.items()]
    return " · ".join(parts)


class NeuroFlowPage(ScrollPage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dataset_path = ""
        self._fingerprint: dict[str, Any] = {}
        self._plan: dict[str, Any] = {"v": 1, "steps": []}
        self._plan_user_owned = False
        self._plan_path: str | None = None
        self._job: WorkerJob | None = None
        self._job_token = 0
        self._job_kind = ""
        self._run_input = ""
        self._run_output = ""
        self._run_meta = ""

        self.content_layout.addWidget(
            PageHeader("NeuroFlow", "Build and run reproducible EEG preprocessing plans.")
        )
        self._build_recording()
        self._build_fingerprint()
        self._build_plan()
        self._build_run()
        self.content_layout.addStretch(1)
        self._refresh_actions()

    def _build_recording(self) -> None:
        self.content_layout.addWidget(self.section_label("Recording"))
        self._recording_stack = QStackedWidget(self)
        empty = QFrame(self)
        empty.setObjectName("emptyPanel")
        empty_l = QVBoxLayout(empty)
        title = QLabel("No recording selected", empty)
        title.setObjectName("emptyPanelTitle")
        hint = QLabel(import_format_hint(), empty)
        hint.setObjectName("emptyPanelHint")
        hint.setWordWrap(True)
        choose = QPushButton("Choose file", empty)
        choose.setObjectName("primaryButton")
        choose.clicked.connect(self.import_recording)
        empty_l.addWidget(title)
        empty_l.addWidget(hint)
        empty_l.addWidget(choose, alignment=Qt.AlignmentFlag.AlignLeft)

        selected = QFrame(self)
        selected.setObjectName("filePanel")
        sel_l = QVBoxLayout(selected)
        top = QHBoxLayout()
        self._file_name = QLabel("", selected)
        self._file_name.setObjectName("fileNameLabel")
        self._file_badge = QLabel("", selected)
        self._file_badge.setObjectName("fileBadge")
        top.addWidget(self._file_name, 1)
        top.addWidget(self._file_badge)
        self._file_meta = QLabel("", selected)
        self._file_meta.setObjectName("fileMetaLabel")
        self._file_path = QLabel("", selected)
        self._file_path.setObjectName("filePathLabel")
        self._file_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        btns = QHBoxLayout()
        change = QPushButton("Change", selected)
        change.setObjectName("secondaryButton")
        change.clicked.connect(self.import_recording)
        clear = QPushButton("Clear", selected)
        clear.setObjectName("secondaryButton")
        clear.clicked.connect(self.clear_all)
        btns.addWidget(change)
        btns.addWidget(clear)
        btns.addStretch(1)
        sel_l.addLayout(top)
        sel_l.addWidget(self._file_meta)
        sel_l.addWidget(self._file_path)
        sel_l.addLayout(btns)

        self._recording_stack.addWidget(empty)
        self._recording_stack.addWidget(selected)
        self.content_layout.addWidget(self._recording_stack)

    def _build_fingerprint(self) -> None:
        self.content_layout.addWidget(self.section_label("Fingerprint"))
        self._fp_status = QLabel("Select a recording to read metadata.", self)
        self._fp_status.setObjectName("fileMetaLabel")
        self._fp_skeleton = SkeletonLoader(self)
        self._fp_skeleton.hide()
        self._fp_panel = QFrame(self)
        self._fp_panel.setObjectName("fingerprintPanel")
        self._fp_panel.hide()
        grid = QGridLayout(self._fp_panel)
        self._fp_values: dict[str, QLabel] = {}
        fields = [
            ("channels", "Channels"),
            ("sfreq", "Sampling rate"),
            ("duration", "Duration"),
            ("montage", "Montage"),
            ("filters", "Filters"),
        ]
        for row, (key, label) in enumerate(fields):
            k = QLabel(label, self._fp_panel)
            k.setObjectName("fingerprintKey")
            v = QLabel("—", self._fp_panel)
            v.setObjectName("fingerprintValue")
            grid.addWidget(k, row, 0)
            grid.addWidget(v, row, 1)
            self._fp_values[key] = v
        self._fp_channels = QLabel("", self._fp_panel)
        self._fp_channels.setObjectName("fingerprintChannels")
        self._fp_channels.setWordWrap(True)
        grid.addWidget(self._fp_channels, len(fields), 0, 1, 2)
        self.content_layout.addWidget(self._fp_status)
        self.content_layout.addWidget(self._fp_skeleton)
        self.content_layout.addWidget(self._fp_panel)

    def _build_plan(self) -> None:
        self.content_layout.addWidget(self.section_label("Plan"))
        self._plan_status = QLabel("A recommended plan appears after fingerprinting.", self)
        self._plan_status.setObjectName("fileMetaLabel")
        self._plan_list = QVBoxLayout()
        self._plan_list.setSpacing(8)
        host = QWidget(self)
        host.setLayout(self._plan_list)
        self.content_layout.addWidget(self._plan_status)
        self.content_layout.addWidget(host)

        row = QHBoxLayout()
        self._add_step_btn = QPushButton("Add step")
        self._add_step_btn.setObjectName("secondaryButton")
        self._add_step_btn.clicked.connect(self.add_step)
        self._save_plan_btn = QPushButton("Save plan")
        self._save_plan_btn.setObjectName("secondaryButton")
        self._save_plan_btn.clicked.connect(self.save_plan_clicked)
        self._load_plan_btn = QPushButton("Load plan")
        self._load_plan_btn.setObjectName("secondaryButton")
        self._load_plan_btn.clicked.connect(self.load_plan_clicked)
        row.addWidget(self._add_step_btn)
        row.addWidget(self._save_plan_btn)
        row.addWidget(self._load_plan_btn)
        row.addStretch(1)
        self.content_layout.addLayout(row)

    def _build_run(self) -> None:
        self.content_layout.addWidget(self.section_label("Run"))
        self._run_status = QLabel("Ready when a recording and plan are available.", self)
        self._run_status.setObjectName("fileMetaLabel")
        self._run_skeleton = SkeletonLoader(self)
        self._run_skeleton.hide()
        self._run_result = QLabel("", self)
        self._run_result.setObjectName("filePathLabel")
        self._run_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._run_result.setWordWrap(True)
        self._run_log_label = QLabel("", self)
        self._run_log_label.setObjectName("fileMetaLabel")
        self._run_log_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._run_log_label.setWordWrap(True)
        row = QHBoxLayout()
        self._run_btn = QPushButton("Run plan")
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.clicked.connect(self.run_plan)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("secondaryButton")
        self._cancel_btn.clicked.connect(self.cancel_job)
        self._cancel_btn.setEnabled(False)
        row.addWidget(self._run_btn)
        row.addWidget(self._cancel_btn)
        row.addStretch(1)
        self.content_layout.addWidget(self._run_status)
        self.content_layout.addWidget(self._run_skeleton)
        self.content_layout.addWidget(self._run_result)
        self.content_layout.addWidget(self._run_log_label)
        self.content_layout.addLayout(row)

    def import_recording(self) -> None:
        project = ProjectDir.instance()
        if not project.root:
            QMessageBox.warning(self, "Project required", "Choose a project folder first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose EEG recording",
            str(project.datasets_dir()),
            import_file_filter(),
        )
        if not path:
            return
        if self._busy():
            QMessageBox.information(self, "Busy", "Wait for the current job to finish.")
            return
        self._fp_status.setText("Importing recording…")
        self._fp_skeleton.show()
        job = import_recording_job(path)
        self._job_kind = "import"
        start_bound_job(
            self,
            "_job",
            job,
            lambda result: self.set_dataset_path(
                str(result.get("path") or ""), bool(result.get("copied"))
            ),
            self._on_import_fail,
            self._refresh_actions,
        )

    def _on_import_fail(self, code: str, message: str) -> None:
        self._fp_skeleton.hide()
        self._fp_status.setText(f"Import failed ({code}): {message}")
        QMessageBox.warning(self, "Import failed", message)

    def set_dataset_path(self, path: str, copied: bool) -> None:
        if not path:
            return
        self._dataset_path = path
        self._fingerprint = {}
        if not self._plan_user_owned:
            self._plan = {"v": 1, "steps": []}
            self.render_plan()
        p = Path(path)
        self._file_name.setText(p.name)
        self._file_name.setToolTip(p.name)
        self._file_badge.setText(extension_badge(path))
        size = format_bytes(p.stat().st_size) if p.is_file() else ""
        status = "Copied into project" if copied else "Using project file"
        self._file_meta.setText(f"{size} · {status}" if size else status)
        self._file_path.setText(path)
        self._file_path.setToolTip(path)
        self._recording_stack.setCurrentIndex(1)
        self.request_fingerprint()
        self._refresh_actions()

    def clear_all(self) -> None:
        if self._busy():
            QMessageBox.information(self, "Busy", "Wait for the current job to finish.")
            return
        self.cancel_job()
        self._dataset_path = ""
        self._fingerprint = {}
        if not self._plan_user_owned:
            self._plan = {"v": 1, "steps": []}
        self._run_output = ""
        self._run_meta = ""
        self._recording_stack.setCurrentIndex(0)
        self._fp_panel.hide()
        self._fp_skeleton.hide()
        self._fp_status.setText("Select a recording to read metadata.")
        self._run_status.setText("Ready when a recording and plan are available.")
        self._run_result.clear()
        self._run_log_label.clear()
        self._run_skeleton.hide()
        self.render_plan()
        self._refresh_actions()

    def request_fingerprint(self) -> None:
        if not self._dataset_path:
            return
        if self._job and self._job.is_running():
            return
        self._fp_status.setText("Reading metadata…")
        self._fp_panel.hide()
        self._fp_skeleton.show()
        self._job_kind = "fingerprint"
        job = fingerprint_job(self._dataset_path)
        start_bound_job(
            self,
            "_job",
            job,
            self._on_fingerprint_ok,
            self._on_fingerprint_fail,
            self._refresh_actions,
        )

    def _on_fingerprint_ok(self, result: dict[str, Any]) -> None:
        self._fp_skeleton.hide()
        self._fingerprint = result
        n_ch = result.get("n_channels", "—")
        sfreq = result.get("sfreq")
        duration = result.get("duration_sec")
        self._fp_values["channels"].setText(str(n_ch))
        self._fp_values["sfreq"].setText(f"{sfreq:g} Hz" if sfreq is not None else "—")
        self._fp_values["duration"].setText(
            f"{duration:.1f} s" if duration is not None else "—"
        )
        self._fp_values["montage"].setText(str(result.get("montage_hint") or "—"))
        hp = result.get("highpass")
        lp = result.get("lowpass")
        self._fp_values["filters"].setText(f"HP {hp} · LP {lp}")
        names = result.get("ch_names") or []
        shown = ", ".join(names[:12])
        if len(names) > 12:
            shown += f"  (+{len(names) - 12} more)"
        self._fp_channels.setText(shown)
        self._fp_channels.setToolTip(", ".join(names))
        self._fp_status.setText("Fingerprint ready.")
        self._fp_panel.show()
        if not self._plan_user_owned:
            self._plan = from_fingerprint(result)
            self.render_plan()
        self._refresh_actions()

    def _on_fingerprint_fail(self, code: str, message: str) -> None:
        self._fp_skeleton.hide()
        self._fingerprint = {}
        if not self._plan_user_owned:
            self._plan = {"v": 1, "steps": []}
            self.render_plan()
        self._fp_status.setText(f"Fingerprint failed ({code}): {message}")

    def render_plan(self) -> None:
        clear_layout(self._plan_list)

        steps = self._plan.get("steps") or []
        if not steps:
            self._plan_status.setText("No steps yet. Fingerprint a recording or add steps.")
            self._plan_status.setToolTip("")
            return

        self._plan_status.setText(f"{len(steps)} steps")
        self._plan_status.setToolTip(json.dumps(self._plan, indent=2))
        for index, step in enumerate(steps):
            row = QFrame(self)
            row.setObjectName("planStepRow")
            layout = QHBoxLayout(row)
            idx = QLabel(str(index + 1), row)
            idx.setObjectName("planStepIndex")
            idx.setFixedSize(24, 24)
            idx.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text = QVBoxLayout()
            title = QLabel(step.get("title") or step.get("step_id", ""), row)
            title.setObjectName("planStepTitle")
            meta = QLabel(_summarize_params(step.get("params") or {}), row)
            meta.setObjectName("planStepMeta")
            meta.setWordWrap(True)
            rationale = QLabel(step.get("rationale") or "", row)
            rationale.setObjectName("planStepRationale")
            rationale.setWordWrap(True)
            text.addWidget(title)
            text.addWidget(meta)
            if step.get("rationale"):
                text.addWidget(rationale)
            btns = QHBoxLayout()
            for label, slot in (
                ("Up", lambda i=index: self.move_step(i, -1)),
                ("Down", lambda i=index: self.move_step(i, 1)),
                ("Edit", lambda i=index: self.edit_step(i)),
                ("Remove", lambda i=index: self.remove_step(i)),
            ):
                b = QPushButton(label, row)
                b.setObjectName("planStepButton")
                b.clicked.connect(slot)
                if label == "Up":
                    b.setEnabled(index > 0)
                if label == "Down":
                    b.setEnabled(index < len(steps) - 1)
                btns.addWidget(b)
            layout.addWidget(idx)
            layout.addLayout(text, 1)
            layout.addLayout(btns)
            self._plan_list.addWidget(row)

    def add_step(self) -> None:
        if self._busy():
            return
        catalog = step_catalog()
        labels = [f"{s['title']} ({s['id']})" for s in catalog]
        choice, ok = QInputDialog.getItem(self, "Add step", "Step:", labels, 0, False)
        if not ok or not choice:
            return
        step_id = choice.rsplit("(", 1)[-1].rstrip(")")
        step = make_step(step_id, default_params(step_id), "Added manually.")
        self._plan.setdefault("steps", []).append(step)
        self._plan_user_owned = True
        self.render_plan()
        self._refresh_actions()

    def edit_step(self, index: int) -> None:
        if self._busy():
            return
        steps = self._plan.get("steps") or []
        if index < 0 or index >= len(steps):
            return
        step = steps[index]
        step_id = step["step_id"]
        defn = find_step(step_id)
        if defn is None:
            return
        dialog = SchemaEditDialog(
            f"Edit {defn['title']}",
            defn.get("description") or "",
            defn.get("params") or [],
            step.get("params") or {},
            lambda values: validate_step_params(step_id, values),
            self,
        )
        if dialog.exec():
            step["params"] = dialog.values()
            self._plan_user_owned = True
            self.render_plan()

    def move_step(self, index: int, delta: int) -> None:
        if self._busy():
            return
        steps = self._plan.get("steps") or []
        j = index + delta
        if j < 0 or j >= len(steps):
            return
        steps[index], steps[j] = steps[j], steps[index]
        self._plan_user_owned = True
        self.render_plan()

    def remove_step(self, index: int) -> None:
        if self._busy():
            return
        reply = QMessageBox.question(
            self,
            "Remove step",
            "Remove this step from the plan?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        steps = self._plan.get("steps") or []
        if 0 <= index < len(steps):
            del steps[index]
            self._plan_user_owned = True
            self.render_plan()
            self._refresh_actions()

    def save_plan_clicked(self) -> None:
        err = validate_plan(self._plan)
        if err:
            QMessageBox.warning(self, "Invalid plan", err)
            return
        base = Path(self._dataset_path).stem if self._dataset_path else "plan"
        payload = dict(self._plan)
        if self._dataset_path:
            payload["dataset_path"] = self._dataset_path
            payload["name"] = f"{base}_plan"
        try:
            path = save_plan(payload, base)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return
        self._plan_path = str(path)
        self._plan_status.setText(f"Saved {path.name}")
        QMessageBox.information(self, "Plan saved", str(path))

    def load_plan_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load plan",
            str(ProjectDir.instance().plans_dir()),
            "Plans (*.json)",
        )
        if not path:
            return
        try:
            plan = load_plan(path)
        except (OSError, ValueError, PermissionError) as exc:
            QMessageBox.warning(self, "Load failed", str(exc))
            return
        self._plan = plan
        self._plan_path = path
        self._plan_user_owned = True
        self.render_plan()
        self._refresh_actions()

    def run_plan(self) -> None:
        if not self._dataset_path or not (self._plan.get("steps") or []):
            return
        if self._job and self._job.is_running():
            return
        err = validate_plan(self._plan)
        if err:
            QMessageBox.warning(self, "Invalid plan", err)
            return
        try:
            out_path, meta_path = suggest_run_paths(Path(self._dataset_path).stem)
        except OSError as exc:
            QMessageBox.warning(self, "Run failed", str(exc))
            return
        self._run_input = self._dataset_path
        self._run_output = str(out_path)
        self._run_meta = str(meta_path)
        self._run_status.setText("Running plan…")
        self._run_skeleton.show()
        self._run_result.clear()
        self._run_log_label.clear()
        self._cancel_btn.setEnabled(True)
        self._run_btn.setEnabled(False)
        self._job_kind = "run"

        job = run_plan_job(
            self._run_input,
            self._run_output,
            self._plan,
            meta_path=self._run_meta,
        )
        job.progress.connect(self._on_run_progress)
        start_bound_job(
            self,
            "_job",
            job,
            self._on_run_ok,
            self._on_run_fail,
            self._refresh_actions,
        )

    def _on_run_progress(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or payload.get("stage") or "Working…")
        self._run_status.setText(message)
        log = (self._run_log_label.text() + "\n" + message).strip()
        self._run_log_label.setText(log[-4000:])

    def _on_run_ok(self, result: dict[str, Any]) -> None:
        self._run_skeleton.hide()
        self._cancel_btn.setEnabled(False)
        project = ProjectDir.instance()
        out = result.get("output_path") or self._run_output
        meta = result.get("meta_path") or self._run_meta
        if not project.contains(out):
            self._run_status.setText("Run finished but output left the project sandbox.")
            self._refresh_actions()
            return
        kind = result.get("output_kind", "?")
        lines = [
            f"Finished · {result.get('n_steps')} steps · {kind}",
            f"Input: {self._run_input}",
            f"Output: {out}",
            f"Metadata: {meta}",
            f"sfreq={result.get('sfreq')}  mne={result.get('mne_version')}",
        ]
        if "n_epochs" in result:
            lines.append(f"epochs={result.get('n_epochs')}")
        elif "duration_sec" in result:
            lines.append(f"duration={result.get('duration_sec')} s")
        self._run_result.setText("\n".join(lines))
        self._run_status.setText("Run complete.")
        self._refresh_actions()

    def _on_run_fail(self, code: str, message: str) -> None:
        self._run_skeleton.hide()
        self._cancel_btn.setEnabled(False)
        if code == "cancelled":
            self._run_status.setText("Run cancelled.")
        else:
            self._run_status.setText(f"Run failed ({code}): {message}")
        self._refresh_actions()

    def _busy(self) -> bool:
        return self._job is not None and self._job.is_running()

    def cancel_job(self) -> None:
        if not self._busy():
            return
        kind = self._job_kind or "job"
        if cancel_bound_job(self, "_job"):
            if kind == "run":
                self._run_status.setText("Cancelling…")
                self._run_skeleton.hide()
            elif kind in {"fingerprint", "import"}:
                self._fp_skeleton.hide()
                self._fp_status.setText("Cancelled.")
            self._cancel_btn.setEnabled(False)
            self._refresh_actions()

    def _refresh_actions(self) -> None:
        busy = self._busy()
        has_plan = bool(self._plan.get("steps"))
        self._run_btn.setEnabled(bool(self._dataset_path) and has_plan and not busy)
        self._save_plan_btn.setEnabled(has_plan and not busy)
        self._cancel_btn.setEnabled(busy)

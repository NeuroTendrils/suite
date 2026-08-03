"""NeuroFlow: recording → fingerprint → plan → run, presented as a staged flow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.eeg_formats import (
    extension_badge,
    import_file_filter,
    import_format_hint,
)
from neurotendrils.core.formatting import format_bytes, format_relative
from neurotendrils.core.jobs import (
    WorkerJob,
    cancel_bound_job,
    fingerprint_job,
    import_recording_job,
    run_plan_job,
    start_bound_job,
)
from neurotendrils.core.library import scan_datasets, scan_runs
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
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.layoututil import clear_layout
from neurotendrils.widgets.modals import alert, confirm, edit_schema, prompt_choice
from neurotendrils.widgets.motion import stagger_in
from neurotendrils.widgets.rows import ListRow, RowList
from neurotendrils.widgets.section import SectionHeader
from neurotendrils.widgets.skeleton import SkeletonLoader
from neurotendrils.widgets.stage_flow import StageFlow

RECORDING = "recording"
FINGERPRINT = "fingerprint"
PLAN = "plan"
RUN = "run"

_RECENT_LIMIT = 4


def _summarize_params(params: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in params.items()]
    return " · ".join(parts)


class _PlanStepRow(QFrame):
    """A plan step; row actions appear on hover to keep the list quiet."""

    moveUpRequested = Signal()
    moveDownRequested = Signal()
    editRequested = Signal()
    removeRequested = Signal()

    def __init__(
        self,
        index: int,
        step: dict[str, Any],
        *,
        can_move_up: bool,
        can_move_down: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("planStepRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(12)

        number = QLabel(str(index + 1), self)
        number.setObjectName("planStepIndex")
        number.setFixedSize(20, 20)
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(step.get("title") or step.get("step_id", ""), self)
        title.setObjectName("planStepTitle")
        meta = QLabel(_summarize_params(step.get("params") or {}), self)
        meta.setObjectName("planStepMeta")
        text.addWidget(title)
        text.addWidget(meta)
        if step.get("rationale"):
            rationale = QLabel(step["rationale"], self)
            rationale.setObjectName("planStepRationale")
            text.addWidget(rationale)
        layout.addLayout(text, 1)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(4)
        specs = (
            ("Up", self.moveUpRequested, can_move_up),
            ("Down", self.moveDownRequested, can_move_down),
            ("Edit", self.editRequested, True),
            ("Remove", self.removeRequested, True),
        )
        self._buttons: list[QPushButton] = []
        for label, signal, enabled in specs:
            button = QPushButton(label, actions)
            button.setObjectName("planStepButton")
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setEnabled(enabled)
            button.clicked.connect(signal.emit)
            actions_layout.addWidget(button)
            self._buttons.append(button)
        # Fixed width keeps the row stable: hidden children free their space,
        # so revealing the actions would otherwise reflow the text column.
        actions.setFixedWidth(actions.sizeHint().width())
        self._reveal_actions(False)
        layout.addWidget(actions, 0, Qt.AlignmentFlag.AlignTop)

    def _reveal_actions(self, visible: bool) -> None:
        for button in self._buttons:
            button.setVisible(visible)

    def enterEvent(self, event) -> None:  # noqa: ANN001, N802
        super().enterEvent(event)
        self._reveal_actions(True)

    def leaveEvent(self, event) -> None:  # noqa: ANN001, N802
        super().leaveEvent(event)
        self._reveal_actions(False)


def _set_text(label: QLabel, text: str) -> None:
    """Empty labels still take vertical space, so hide them."""
    label.setText(text)
    label.setVisible(bool(text))


def _stage_widget(parent: QWidget | None = None) -> tuple[QWidget, QVBoxLayout]:
    host = QWidget(parent)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)
    return host, layout


class NeuroFlowPage(QWidget):
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
        self._run_done = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.flow = StageFlow(
            "NeuroFlow",
            "Import a recording, read its fingerprint, shape a plan, then run it.",
            self,
        )
        self.flow.add_stage(
            RECORDING, "Recording", self._build_recording(), primary="Choose file"
        )
        self.flow.add_stage(
            FINGERPRINT, "Fingerprint", self._build_fingerprint(), primary="Continue"
        )
        self.flow.add_stage(PLAN, "Plan", self._build_plan(), primary="Continue")
        self.flow.add_stage(RUN, "Run", self._build_run(), primary="Run plan")
        self.flow.finalize()
        self.flow.primaryTriggered.connect(self._on_primary)
        self.flow.stageChanged.connect(self._on_stage_changed)
        layout.addWidget(self.flow)

        ProjectDir.instance().root_changed.connect(lambda *_: self._refresh_pickers())
        self.render_plan()
        self._refresh_actions()

    # ---------- stages ----------

    def _build_recording(self) -> QWidget:
        host, layout = _stage_widget(self)

        self._recording_stack = QStackedWidget(host)
        empty = QFrame(host)
        empty.setObjectName("emptyPanel")
        empty_l = QVBoxLayout(empty)
        empty_l.setContentsMargins(20, 18, 20, 18)
        empty_l.setSpacing(8)
        title = QLabel("No recording selected", empty)
        title.setObjectName("emptyPanelTitle")
        hint = QLabel(import_format_hint(), empty)
        hint.setObjectName("emptyPanelHint")
        hint.setWordWrap(True)
        choose = QPushButton("Browse files…", empty)
        choose.setObjectName("secondaryButton")
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        choose.clicked.connect(self.import_recording)
        empty_l.addWidget(title)
        empty_l.addWidget(hint)
        empty_l.addWidget(choose, alignment=Qt.AlignmentFlag.AlignLeft)

        selected = QFrame(host)
        selected.setObjectName("filePanel")
        sel_l = QVBoxLayout(selected)
        sel_l.setContentsMargins(20, 18, 20, 18)
        sel_l.setSpacing(6)
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
        self._file_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        btns = QHBoxLayout()
        btns.setSpacing(8)
        change = QPushButton("Change", selected)
        change.setObjectName("secondaryButton")
        change.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        change.clicked.connect(self.import_recording)
        clear = QPushButton("Clear", selected)
        clear.setObjectName("secondaryButton")
        clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        clear.clicked.connect(self.clear_all)
        btns.addWidget(change)
        btns.addWidget(clear)
        btns.addStretch(1)
        sel_l.addLayout(top)
        sel_l.addWidget(self._file_meta)
        sel_l.addWidget(self._file_path)
        sel_l.addSpacing(6)
        sel_l.addLayout(btns)

        self._recording_stack.addWidget(empty)
        self._recording_stack.addWidget(selected)
        self._recording_stack.setMaximumWidth(640)
        layout.addWidget(self._recording_stack)

        layout.addSpacing(16)
        recent_header = SectionHeader("In this project", "Refresh", host)
        recent_header.actionTriggered.connect(self._refresh_pickers)
        layout.addWidget(recent_header)
        self._dataset_rows = RowList(host)
        layout.addWidget(self._dataset_rows)
        return host

    def _build_fingerprint(self) -> QWidget:
        host, layout = _stage_widget(self)

        self._fp_status = QLabel("Select a recording to read metadata.", host)
        self._fp_status.setObjectName("fileMetaLabel")
        self._fp_skeleton = SkeletonLoader(host)
        self._fp_skeleton.hide()

        self._fp_panel = QFrame(host)
        self._fp_panel.setObjectName("fingerprintPanel")
        self._fp_panel.setMaximumWidth(640)
        self._fp_panel.hide()
        grid = QGridLayout(self._fp_panel)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
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

        reread = QPushButton("Re-read metadata", host)
        reread.setObjectName("secondaryButton")
        reread.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        reread.clicked.connect(self.request_fingerprint)
        self._fp_reread = reread

        layout.addWidget(self._fp_status)
        layout.addWidget(self._fp_skeleton)
        layout.addWidget(self._fp_panel)
        layout.addWidget(reread, alignment=Qt.AlignmentFlag.AlignLeft)
        return host

    def _build_plan(self) -> QWidget:
        host, layout = _stage_widget(self)

        self._plan_status = QLabel(
            "A recommended plan appears after fingerprinting.", host
        )
        self._plan_status.setObjectName("fileMetaLabel")

        steps_host = QWidget(host)
        self._plan_list = QVBoxLayout(steps_host)
        self._plan_list.setContentsMargins(0, 0, 0, 0)
        self._plan_list.setSpacing(0)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._add_step_btn = QPushButton("Add step", host)
        self._add_step_btn.setObjectName("secondaryButton")
        self._add_step_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._add_step_btn.clicked.connect(self.add_step)
        self._save_plan_btn = QPushButton("Save plan", host)
        self._save_plan_btn.setObjectName("secondaryButton")
        self._save_plan_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._save_plan_btn.clicked.connect(self.save_plan_clicked)
        self._load_plan_btn = QPushButton("Load plan", host)
        self._load_plan_btn.setObjectName("secondaryButton")
        self._load_plan_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._load_plan_btn.clicked.connect(self.load_plan_clicked)
        row.addWidget(self._add_step_btn)
        row.addWidget(self._save_plan_btn)
        row.addWidget(self._load_plan_btn)
        row.addStretch(1)

        layout.addWidget(self._plan_status)
        layout.addWidget(steps_host)
        layout.addLayout(row)
        return host

    def _build_run(self) -> QWidget:
        host, layout = _stage_widget(self)

        self._run_status = QLabel("Ready when a recording and plan are available.", host)
        self._run_status.setObjectName("fileMetaLabel")
        self._run_skeleton = SkeletonLoader(host)
        self._run_skeleton.hide()
        self._run_result = QLabel("", host)
        self._run_result.setObjectName("filePathLabel")
        self._run_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._run_result.setWordWrap(True)
        self._run_log_label = QLabel("", host)
        self._run_log_label.setObjectName("fileMetaLabel")
        self._run_log_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._run_log_label.setWordWrap(True)
        self._run_result.hide()
        self._run_log_label.hide()

        self._cancel_btn = QPushButton("Cancel run", host)
        self._cancel_btn.setObjectName("secondaryButton")
        self._cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._cancel_btn.clicked.connect(self.cancel_job)
        self._cancel_btn.hide()

        layout.addWidget(self._run_status)
        layout.addWidget(self._run_skeleton)
        layout.addWidget(self._run_result)
        layout.addWidget(self._run_log_label)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addSpacing(16)
        runs_header = SectionHeader("Run outputs", "Refresh", host)
        runs_header.actionTriggered.connect(self._refresh_pickers)
        layout.addWidget(runs_header)
        self._run_rows = RowList(host)
        layout.addWidget(self._run_rows)
        return host

    # ---------- flow chrome ----------

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._refresh_pickers()

    def _on_stage_changed(self, key: str) -> None:
        if key in {RECORDING, RUN}:
            self._refresh_pickers()
        self._refresh_actions()

    def _on_primary(self, key: str) -> None:
        if key == RECORDING:
            if not self._dataset_path:
                self.import_recording()
            else:
                self.flow.advance()
            return
        if key == FINGERPRINT:
            if not self._fingerprint and self._dataset_path:
                self.request_fingerprint()
            else:
                self.flow.advance()
            return
        if key == PLAN:
            self.flow.advance()
            return
        if key == RUN:
            self.run_plan()

    def _refresh_pickers(self) -> None:
        self._dataset_rows.clear()
        datasets = scan_datasets()[:_RECENT_LIMIT]
        if not datasets:
            self._dataset_rows.add_placeholder(
                "No recordings in the project folder yet."
            )
        else:
            for entry in datasets:
                row = ListRow(
                    entry.title,
                    entry.subtitle,
                    format_bytes(entry.size_bytes),
                    Glyph.DATASETS,
                    self._dataset_rows,
                )
                row.activated.connect(
                    lambda path=entry.path: self.set_dataset_path(path, False)
                )
                self._dataset_rows.add_row(row)
            stagger_in(self._dataset_rows.rows())

        self._run_rows.clear()
        runs = scan_runs()[:_RECENT_LIMIT]
        if not runs:
            self._run_rows.add_placeholder("Run outputs will be listed here.")
            return
        for entry in runs:
            row = ListRow(
                entry.title,
                entry.subtitle,
                f"{format_bytes(entry.size_bytes)}   ·   {format_relative(entry.modified)}",
                Glyph.RUNS,
                self._run_rows,
            )
            row.activated.connect(lambda path=entry.path: self._show_run(path))
            self._run_rows.add_row(row)
        stagger_in(self._run_rows.rows())

    def _show_run(self, path: str) -> None:
        _set_text(self._run_result, path)
        self._run_status.setText(f"Selected {Path(path).name}")

    def _context_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if self._dataset_path:
            name = Path(self._dataset_path).name
            items.append(("Recording", name))
            items.append(("Format", extension_badge(self._dataset_path)))
        if self._fingerprint:
            sfreq = self._fingerprint.get("sfreq")
            duration = self._fingerprint.get("duration_sec")
            items.append(("Channels", str(self._fingerprint.get("n_channels", "—"))))
            items.append(("Rate", f"{sfreq:g} Hz" if sfreq is not None else "—"))
            if duration is not None:
                items.append(("Duration", f"{duration:.0f} s"))
        steps = self._plan.get("steps") or []
        if steps:
            items.append(("Steps", str(len(steps))))
        return items

    def _sync_flow(self) -> None:
        busy = self._busy()
        has_data = bool(self._dataset_path)
        has_plan = bool(self._plan.get("steps"))

        self.flow.set_complete(RECORDING, has_data)
        self.flow.set_complete(FINGERPRINT, bool(self._fingerprint))
        self.flow.set_complete(PLAN, has_plan)
        self.flow.set_complete(RUN, self._run_done)

        self.flow.set_unlocked(FINGERPRINT, has_data)
        self.flow.set_unlocked(PLAN, has_data)
        self.flow.set_unlocked(RUN, has_data and has_plan)

        self.flow.set_context(self._context_items())

        stage = self.flow.current_key()
        if stage == RECORDING:
            if busy:
                self.flow.set_primary("Working…", enabled=False)
            elif has_data:
                self.flow.set_primary("Continue", enabled=True)
            else:
                self.flow.set_primary("Choose file", enabled=True)
            self.flow.set_status(self._fp_status.text() if busy else "")
        elif stage == FINGERPRINT:
            if busy:
                self.flow.set_primary("Reading…", enabled=False)
            elif not self._fingerprint:
                self.flow.set_primary("Read metadata", enabled=has_data)
            else:
                self.flow.set_primary("Continue", enabled=True)
            self.flow.set_status(self._fp_status.text() if busy else "")
        elif stage == PLAN:
            self.flow.set_primary("Continue", enabled=has_plan)
            self.flow.set_status("")
        else:
            running = busy and self._job_kind == "run"
            if running:
                self.flow.set_primary("Running…", enabled=False)
            else:
                self.flow.set_primary(
                    "Run plan", enabled=has_data and has_plan and not busy
                )
            self.flow.set_status(self._run_status.text() if running else "")

    # ---------- recording ----------

    def import_recording(self) -> None:
        project = ProjectDir.instance()
        if not project.root:
            alert(self, "Project required", "Choose a project folder first.")
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
            alert(self, "Busy", "Wait for the current job to finish.")
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
        alert(self, "Import failed", message)

    def set_dataset_path(self, path: str, copied: bool) -> None:
        if not path:
            return
        self._dataset_path = path
        self._fingerprint = {}
        self._run_done = False
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
        self._refresh_pickers()
        # Move to the fingerprint stage and read metadata once the import thread is done.
        self.flow.go_to(FINGERPRINT)
        QTimer.singleShot(0, self.request_fingerprint)
        self._refresh_actions()

    def clear_all(self) -> None:
        if self._busy():
            alert(self, "Busy", "Wait for the current job to finish.")
            return
        self.cancel_job()
        self._dataset_path = ""
        self._fingerprint = {}
        if not self._plan_user_owned:
            self._plan = {"v": 1, "steps": []}
        self._run_output = ""
        self._run_meta = ""
        self._run_done = False
        self._recording_stack.setCurrentIndex(0)
        self._fp_panel.hide()
        self._fp_skeleton.hide()
        self._fp_status.setText("Select a recording to read metadata.")
        self._run_status.setText("Ready when a recording and plan are available.")
        _set_text(self._run_result, "")
        _set_text(self._run_log_label, "")
        self._run_skeleton.hide()
        self.render_plan()
        self.flow.go_to(RECORDING)
        self._refresh_actions()

    # ---------- fingerprint ----------

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
        stagger_in([self._fp_panel])
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
        self._refresh_actions()

    # ---------- plan ----------

    def render_plan(self) -> None:
        clear_layout(self._plan_list)

        steps = self._plan.get("steps") or []
        if not steps:
            self._plan_status.setText(
                "No steps yet. Fingerprint a recording or add steps."
            )
            self._plan_status.show()
            self.setToolTip("")
            return

        self._plan_status.setText("")
        self._plan_status.hide()
        self.setToolTip(json.dumps(self._plan, indent=2))
        rows: list[QWidget] = []
        for index, step in enumerate(steps):
            row = _PlanStepRow(
                index,
                step,
                can_move_up=index > 0,
                can_move_down=index < len(steps) - 1,
            )
            row.moveUpRequested.connect(lambda i=index: self.move_step(i, -1))
            row.moveDownRequested.connect(lambda i=index: self.move_step(i, 1))
            row.editRequested.connect(lambda i=index: self.edit_step(i))
            row.removeRequested.connect(lambda i=index: self.remove_step(i))
            self._plan_list.addWidget(row)
            rows.append(row)
        stagger_in(rows, gap=35)

    def add_step(self) -> None:
        if self._busy():
            return
        catalog = step_catalog()
        labels = [f"{s['title']} ({s['id']})" for s in catalog]
        choice, ok = prompt_choice(self, "Add step", "Step:", labels)
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
        values = edit_schema(
            self,
            f"Edit {defn['title']}",
            defn.get("description") or "",
            defn.get("params") or [],
            step.get("params") or {},
            lambda vals: validate_step_params(step_id, vals),
        )
        if values is not None:
            step["params"] = values
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
        if not confirm(self, "Remove step", "Remove this step from the plan?"):
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
            alert(self, "Invalid plan", err)
            return
        base = Path(self._dataset_path).stem if self._dataset_path else "plan"
        payload = dict(self._plan)
        if self._dataset_path:
            payload["dataset_path"] = self._dataset_path
            payload["name"] = f"{base}_plan"
        try:
            path = save_plan(payload, base)
        except (OSError, ValueError) as exc:
            alert(self, "Save failed", str(exc))
            return
        self._plan_path = str(path)
        self._plan_status.setText(f"Saved {path.name}")
        self._plan_status.show()
        self._refresh_actions()
        alert(self, "Plan saved", str(path))

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
            alert(self, "Load failed", str(exc))
            return
        self._plan = plan
        self._plan_path = path
        self._plan_user_owned = True
        self.render_plan()
        self._refresh_actions()

    # ---------- run ----------

    def run_plan(self) -> None:
        if not self._dataset_path or not (self._plan.get("steps") or []):
            return
        if self._job and self._job.is_running():
            return
        err = validate_plan(self._plan)
        if err:
            alert(self, "Invalid plan", err)
            return
        try:
            out_path, meta_path = suggest_run_paths(Path(self._dataset_path).stem)
        except OSError as exc:
            alert(self, "Run failed", str(exc))
            return
        self.flow.go_to(RUN)
        self._run_input = self._dataset_path
        self._run_output = str(out_path)
        self._run_meta = str(meta_path)
        self._run_done = False
        self._run_status.setText("Running plan…")
        self._run_skeleton.show()
        _set_text(self._run_result, "")
        _set_text(self._run_log_label, "")
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
        self.flow.set_status(message)
        log = (self._run_log_label.text() + "\n" + message).strip()
        _set_text(self._run_log_label, log[-4000:])

    def _on_run_ok(self, result: dict[str, Any]) -> None:
        self._run_skeleton.hide()
        self._cancel_btn.setVisible(False)
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
        _set_text(self._run_result, "\n".join(lines))
        stagger_in([self._run_result])
        self._run_status.setText("Run complete.")
        self._run_done = True
        self._refresh_pickers()
        self._refresh_actions()

    def _on_run_fail(self, code: str, message: str) -> None:
        self._run_skeleton.hide()
        self._cancel_btn.setVisible(False)
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
            self._cancel_btn.setVisible(False)
            self._refresh_actions()

    def _refresh_actions(self) -> None:
        busy = self._busy()
        has_plan = bool(self._plan.get("steps"))
        self._save_plan_btn.setEnabled(has_plan and not busy)
        self._add_step_btn.setEnabled(not busy)
        self._load_plan_btn.setEnabled(not busy)
        self._cancel_btn.setVisible(busy and self._job_kind == "run")
        self._fp_reread.setEnabled(bool(self._dataset_path) and not busy)
        self._sync_flow()

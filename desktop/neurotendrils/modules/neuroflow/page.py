"""NeuroFlow: recording → fingerprint → plan → run, presented as a staged flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.dataset_manifest import (
    inspect_manifest_light,
    is_dataset_manifest,
    load_manifest,
    resolve_member_path,
)
from neurotendrils.core.eeg_formats import (
    extension_badge,
    import_file_filter,
    import_format_hint,
)
from neurotendrils.core.formatting import format_bytes, format_number, format_relative
from neurotendrils.core.ingestion.montage import STANDARD_MONTAGES
from neurotendrils.core.jobs import (
    WorkerJob,
    apply_montage_job,
    cancel_bound_job,
    drop_channels_job,
    fingerprint_job,
    import_recording_job,
    persist_bad_spans_job,
    preview_recording_job,
    review_qa_job,
    run_dataset_plan_job,
    run_plan_job,
    start_bound_job,
)
from neurotendrils.core.library import (
    LibraryBus,
    LibraryEntry,
    notify_library_changed,
    scan_datasets,
    scan_runs,
)
from neurotendrils.core.notifications import notify
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
from neurotendrils.widgets.augment_review import AugmentReview
from neurotendrils.widgets.eeg_viewer import EegViewer, ViewerEvent
from neurotendrils.widgets.erp_plot import ErpPlot
from neurotendrils.widgets.ica_browser import IcaBrowser
from neurotendrils.widgets.stage_flow import StageFlow
from neurotendrils.widgets.trial_labels import TrialLabelEditor

RECORDING = "recording"
INSPECT = "inspect"
FINGERPRINT = "fingerprint"
PLAN = "plan"
RUN = "run"
REVIEW = "review"

_RECENT_LIMIT = 4


def _summarize_params(params: dict[str, Any]) -> str:
    parts = [f"{k}={v}" for k, v in params.items()]
    return " · ".join(parts)


def _fingerprint_member_path(manifest) -> Path:
    """Prefer a continuous Raw member for fingerprinting when available."""
    ranked: list[tuple[int, Path]] = []
    for member in manifest.members:
        path = resolve_member_path(manifest, member)
        name = path.name.lower()
        if name.endswith(("_raw.fif", ".fif")) and "-epo" not in name:
            rank = 0 if name.endswith("_raw.fif") else 1
        elif "-epo" in name or name.endswith("_epo.fif"):
            rank = 3
        else:
            rank = 2
        ranked.append((rank, path))
    ranked.sort(key=lambda item: (item[0], item[1].name))
    return ranked[0][1]


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
    trainInStudioRequested = Signal(str)

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
        self._review_loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._inspect_path = ""
        self._pending_bads: list[dict[str, Any]] = []

        self.flow = StageFlow(
            "NeuroFlow",
            "Import → inspect & reject → recipe plan → run → ICA/ERP review → train.",
            self,
        )
        self.flow.add_stage(
            RECORDING, "Recording", self._build_recording(), primary="Choose file"
        )
        self.flow.add_stage(
            INSPECT, "Inspect", self._build_inspect(), primary="Continue"
        )
        self.flow.add_stage(
            FINGERPRINT, "Fingerprint", self._build_fingerprint(), primary="Continue"
        )
        self.flow.add_stage(PLAN, "Plan", self._build_plan(), primary="Continue")
        self.flow.add_stage(RUN, "Run", self._build_run(), primary="Run plan")
        self.flow.add_stage(
            REVIEW, "Review", self._build_review(), primary="Train in NeuroStudio"
        )
        self.flow.finalize()
        self.flow.primaryTriggered.connect(self._on_primary)
        self.flow.stageChanged.connect(self._on_stage_changed)
        layout.addWidget(self.flow)

        ProjectDir.instance().root_changed.connect(lambda *_: self._refresh_pickers())
        LibraryBus.instance().changed.connect(self._refresh_pickers)
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
        title = QLabel("No recording or dataset selected", empty)
        title.setObjectName("emptyPanelTitle")
        hint = QLabel(
            import_format_hint()
            + " Multi-file datasets (dataset.json) can be cleaned here too.",
            empty,
        )
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

    def _build_inspect(self) -> QWidget:
        """EEGLAB-like browse: scroll traces, paint BAD, montage, channel drop, labels."""
        host, layout = _stage_widget(self)

        self._inspect_status = QLabel(
            "Scroll the traces, toggle Paint bad and drag to reject spans, "
            "apply a montage, drop bad channels, and map event labels.",
            host,
        )
        self._inspect_status.setObjectName("fileMetaLabel")
        self._inspect_status.setWordWrap(True)
        layout.addWidget(self._inspect_status)

        tools = QHBoxLayout()
        tools.addWidget(QLabel("Montage", host))
        self._inspect_montage = QComboBox(host)
        self._inspect_montage.addItem("(none)", None)
        for name in STANDARD_MONTAGES:
            self._inspect_montage.addItem(name, name)
        tools.addWidget(self._inspect_montage)
        self._inspect_apply_montage = QPushButton("Apply montage", host)
        self._inspect_apply_montage.setObjectName("secondaryButton")
        self._inspect_apply_montage.clicked.connect(self._apply_inspect_montage)
        tools.addWidget(self._inspect_apply_montage)
        self._inspect_save_bads = QPushButton("Save BAD marks", host)
        self._inspect_save_bads.setObjectName("secondaryButton")
        self._inspect_save_bads.setCursor(Qt.CursorShape.PointingHandCursor)
        self._inspect_save_bads.clicked.connect(self._save_inspect_bads)
        tools.addWidget(self._inspect_save_bads)
        self._inspect_drop_ch = QPushButton("Drop selected channels", host)
        self._inspect_drop_ch.setObjectName("secondaryButton")
        self._inspect_drop_ch.clicked.connect(self._drop_inspect_channels)
        tools.addWidget(self._inspect_drop_ch)
        self._inspect_reload = QPushButton("Reload preview", host)
        self._inspect_reload.setObjectName("ghostButton")
        self._inspect_reload.clicked.connect(self._load_inspect_preview)
        tools.addWidget(self._inspect_reload)
        tools.addStretch(1)
        layout.addLayout(tools)

        body = QHBoxLayout()
        self._inspect_viewer = EegViewer(host)
        self._inspect_viewer.badSpanPainted.connect(self._on_bad_painted)
        self._inspect_viewer.setMinimumHeight(320)
        body.addWidget(self._inspect_viewer, 1)

        ch_col = QVBoxLayout()
        ch_col.addWidget(QLabel("Channels (select to drop)", host))
        self._inspect_channels = QListWidget(host)
        self._inspect_channels.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self._inspect_channels.setMaximumWidth(160)
        ch_col.addWidget(self._inspect_channels, 1)
        body.addLayout(ch_col)
        layout.addLayout(body, 1)

        self._inspect_labels = TrialLabelEditor(host)
        self._inspect_labels.setMaximumHeight(180)
        layout.addWidget(self._inspect_labels)
        return host

    def _build_fingerprint(self) -> QWidget:
        host, layout = _stage_widget(self)

        self._fp_status = QLabel("Select a recording to read metadata.", host)
        self._fp_status.setObjectName("fileMetaLabel")
        self._fp_skeleton = SkeletonLoader(host)
        self._fp_skeleton.hide()

        self._fp_panel = QFrame(host)
        self._fp_panel.setObjectName("fingerprintPanel")
        self._fp_panel.setMaximumWidth(720)
        self._fp_panel.hide()
        panel_l = QVBoxLayout(self._fp_panel)
        panel_l.setContentsMargins(20, 16, 20, 16)
        panel_l.setSpacing(14)

        grid_host = QWidget(self._fp_panel)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(1, 1)
        self._fp_values: dict[str, QLabel] = {}
        fields = [
            ("channels", "Channels"),
            ("sfreq", "Sampling rate"),
            ("duration", "Duration"),
            ("montage", "Montage"),
            ("filters", "Filters"),
        ]
        for row, (key, label) in enumerate(fields):
            k = QLabel(label, grid_host)
            k.setObjectName("fingerprintKey")
            k.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            v = QLabel("—", grid_host)
            v.setObjectName("fingerprintValue")
            v.setWordWrap(True)
            v.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(k, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(v, row, 1)
            self._fp_values[key] = v
        panel_l.addWidget(grid_host)

        self._fp_channels = QLabel("", self._fp_panel)
        self._fp_channels.setObjectName("fingerprintChannels")
        self._fp_channels.setWordWrap(True)
        self._fp_channels.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._fp_channels.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._fp_channels.hide()
        panel_l.addWidget(self._fp_channels)

        reread = QPushButton("Re-read metadata", self._fp_panel)
        reread.setObjectName("secondaryButton")
        reread.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        reread.clicked.connect(self.request_fingerprint)
        self._fp_reread = reread
        panel_l.addWidget(reread, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self._fp_status)
        layout.addWidget(self._fp_skeleton)
        layout.addWidget(self._fp_panel)
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
        runs_header = SectionHeader("Previous runs", "Refresh", host)
        runs_header.actionTriggered.connect(self._refresh_pickers)
        layout.addWidget(runs_header)
        self._run_rows = RowList(host)
        layout.addWidget(self._run_rows)
        return host

    def _build_review(self) -> QWidget:
        host, layout = _stage_widget(self)
        self._review_status = QLabel(
            "After a run, review ICA, ERPs, and suggested augment trials here.",
            host,
        )
        self._review_status.setObjectName("fileMetaLabel")
        self._review_status.setWordWrap(True)
        layout.addWidget(self._review_status)

        self._ica_browser = IcaBrowser(host)
        layout.addWidget(self._ica_browser)
        self._erp_plot = ErpPlot(host)
        layout.addWidget(self._erp_plot)
        self._augment_review = AugmentReview(host)
        layout.addWidget(self._augment_review)

        review_actions = QHBoxLayout()
        self._review_apply_ica = QPushButton("Apply ICA exclude to plan", host)
        self._review_apply_ica.setObjectName("secondaryButton")
        self._review_apply_ica.clicked.connect(self._on_apply_ica_clicked)
        review_actions.addWidget(self._review_apply_ica)
        review_actions.addStretch(1)
        layout.addLayout(review_actions)

        train_hint = QLabel(
            "When satisfied, continue to NeuroStudio to train on the cleaned epochs.",
            host,
        )
        train_hint.setObjectName("mutedLabel")
        train_hint.setWordWrap(True)
        layout.addWidget(train_hint)
        return host

    # ---------- flow chrome ----------

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._refresh_pickers()

    def _on_stage_changed(self, key: str) -> None:
        if key in {RECORDING, RUN}:
            self._refresh_pickers()
        if key == INSPECT and self._dataset_path:
            self._load_inspect_preview()
        if key == REVIEW and self._run_done and not self._review_loaded:
            self._load_review()
        self._refresh_actions()

    def _on_primary(self, key: str) -> None:
        if key == RECORDING:
            if not self._dataset_path:
                self.import_recording()
            else:
                self.flow.go_to(INSPECT)
            return
        if key == INSPECT:
            self._apply_inspect_prep()
            self.flow.go_to(FINGERPRINT)
            QTimer.singleShot(0, self.request_fingerprint)
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
            if self._run_done:
                self.flow.go_to(REVIEW)
            else:
                self.run_plan()
            return
        if key == REVIEW:
            self._apply_review_ica_to_plan()
            self.trainInStudioRequested.emit(self._run_output or self._dataset_path)
            return

    def _refresh_pickers(self) -> None:
        self._dataset_rows.clear()
        datasets = scan_datasets()[:_RECENT_LIMIT]
        if not datasets:
            self._dataset_rows.add_placeholder(
                "No recordings or datasets in the project folder yet."
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
            self._run_rows.add_placeholder(
                "No runs yet. A run is one plan execution — output lands in runs/."
            )
            return
        for entry in runs:
            row = ListRow(
                entry.title,
                entry.subtitle,
                f"{format_bytes(entry.size_bytes)}   ·   {format_relative(entry.modified)}",
                Glyph.RUNS,
                self._run_rows,
            )
            row.activated.connect(lambda e=entry: self._show_run(e))
            self._run_rows.add_row(row)
        stagger_in(self._run_rows.rows())

    def _show_run(self, entry: LibraryEntry) -> None:
        output = str(entry.extra.get("output_path") or entry.path)
        meta = str(entry.extra.get("meta_path") or "")
        lines = [f"Run {entry.title}", f"Output: {output}"]
        if meta:
            lines.append(f"Metadata: {meta}")
        if entry.subtitle:
            lines.append(entry.subtitle)
        _set_text(self._run_result, "\n".join(lines))
        self._run_status.setText(f"Selected {entry.title}")

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
        self.flow.set_complete(INSPECT, has_data and bool(self._inspect_path))
        self.flow.set_complete(FINGERPRINT, bool(self._fingerprint))
        self.flow.set_complete(PLAN, has_plan)
        self.flow.set_complete(RUN, self._run_done)
        self.flow.set_complete(REVIEW, self._review_loaded)

        self.flow.set_unlocked(INSPECT, has_data)
        self.flow.set_unlocked(FINGERPRINT, has_data)
        self.flow.set_unlocked(PLAN, has_data)
        self.flow.set_unlocked(RUN, has_data and has_plan)
        self.flow.set_unlocked(REVIEW, self._run_done)

        self.flow.set_context(self._context_items())

        stage = self.flow.current_key()
        if stage == RECORDING:
            if busy:
                self.flow.set_primary("Working…", enabled=False)
            elif has_data:
                self.flow.set_primary("Inspect data", enabled=True)
            else:
                self.flow.set_primary("Choose file", enabled=True)
            self.flow.set_status(self._fp_status.text() if busy else "")
        elif stage == INSPECT:
            loading = busy and self._job_kind == "preview"
            self.flow.set_primary(
                "Continue to plan", enabled=has_data and not loading
            )
            self.flow.set_status(self._inspect_status.text() if loading else "")
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
        elif stage == REVIEW:
            out = self._run_output or self._dataset_path
            self.flow.set_primary("Train in NeuroStudio", enabled=bool(out))
            self.flow.set_status(self._review_status.text() if self._review_loaded else "")
        else:
            running = busy and self._job_kind == "run"
            if running:
                self.flow.set_primary("Running…", enabled=False)
            elif self._run_done:
                self.flow.set_primary("Review results", enabled=True)
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
            "Choose EEG recording or dataset.json",
            str(project.datasets_dir()),
            "Datasets (dataset.json);;" + import_file_filter(),
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
        if is_dataset_manifest(path):
            try:
                manifest = load_manifest(path)
                summary = inspect_manifest_light(manifest)
            except (OSError, ValueError) as exc:
                alert(self, "Invalid dataset", str(exc))
                return
            self._file_name.setText(summary["name"])
            self._file_name.setToolTip(summary["name"])
            self._file_badge.setText("DATASET")
            self._file_meta.setText(
                f"{summary['n_members']} files · split {summary['split_mode']} · "
                + ("Copied into project" if copied else "Using project dataset")
            )
        else:
            self._file_name.setText(p.name)
            self._file_name.setToolTip(p.name)
            self._file_badge.setText(extension_badge(path))
            size = format_bytes(p.stat().st_size) if p.is_file() else ""
            status = "Copied into project" if copied else "Using project file"
            self._file_meta.setText(f"{size} · {status}" if size else status)
        self._file_path.setText(path)
        self._file_path.setToolTip(path)
        self._recording_stack.setCurrentIndex(1)
        if copied:
            notify_library_changed()
        self._refresh_pickers()
        # Inspect first (visualize / reject) — fingerprint comes after Continue.
        self.flow.go_to(INSPECT)
        QTimer.singleShot(0, self._load_inspect_preview)
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
        fp_path = self._dataset_path
        if is_dataset_manifest(self._dataset_path):
            try:
                manifest = load_manifest(self._dataset_path)
                if not manifest.members:
                    raise ValueError("Dataset has no members")
                fp_path = str(_fingerprint_member_path(manifest))
            except (OSError, ValueError) as exc:
                self._fp_skeleton.hide()
                self._fp_status.setText(f"Fingerprint failed: {exc}")
                alert(self, "Fingerprint failed", str(exc))
                return
        job = fingerprint_job(fp_path)
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
        hp_text = format_number(hp) if hp is not None else "—"
        lp_text = format_number(lp) if lp is not None else "—"
        self._fp_values["filters"].setText(f"HP {hp_text} · LP {lp_text}")
        names = [str(n) for n in (result.get("ch_names") or [])]
        if names:
            shown = ", ".join(names[:12])
            if len(names) > 12:
                shown += f"  (+{len(names) - 12} more)"
            self._fp_channels.setText(shown)
            self._fp_channels.setToolTip(", ".join(names))
            self._fp_channels.show()
        else:
            self._fp_channels.clear()
            self._fp_channels.hide()
        kind = str(result.get("mne_kind") or "raw")
        if kind == "epochs" and result.get("n_epochs") is not None:
            self._fp_status.setText(
                f"Fingerprint ready (epoched · {result.get('n_epochs')} trials)."
            )
        elif is_dataset_manifest(self._dataset_path):
            self._fp_status.setText(
                "Fingerprint ready (sample member from dataset)."
            )
        else:
            self._fp_status.setText("Fingerprint ready.")
        self._fp_panel.show()
        # Avoid opacity fades on the panel — they clip wrapped channel labels.
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
            return

        self._plan_status.setText("")
        self._plan_status.hide()
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
        notify_library_changed()
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

        is_dataset = is_dataset_manifest(self._dataset_path)
        try:
            if is_dataset:
                stem = Path(self._dataset_path).parent.name
            else:
                stem = Path(self._dataset_path).stem
            out_path, meta_path = suggest_run_paths(stem)
        except OSError as exc:
            alert(self, "Run failed", str(exc))
            return
        self.flow.go_to(RUN)
        self._run_input = self._dataset_path
        self._run_output = str(out_path)
        self._run_meta = str(meta_path)
        self._run_done = False
        self._run_status.setText(
            "Cleaning dataset members…" if is_dataset else "Running plan…"
        )
        self._run_skeleton.show()
        _set_text(self._run_result, "")
        _set_text(self._run_log_label, "")
        self._job_kind = "run"

        if is_dataset:
            job = run_dataset_plan_job(
                dataset_path=self._dataset_path,
                plan=self._plan,
            )
        else:
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
        out = result.get("manifest_path") or result.get("output_path") or self._run_output
        meta = result.get("meta_path") or self._run_meta
        if not project.contains(out):
            self._run_status.setText("Run finished but output left the project sandbox.")
            notify(
                "Run finished",
                "Output left the project sandbox.",
                level="error",
            )
            self._refresh_actions()
            return
        kind = result.get("output_kind", "?")
        if kind == "dataset_manifest":
            self._run_output = str(out)
            notify_library_changed()
            name = str(result.get("name") or Path(out).parent.name)
            lines = [
                f"Finished · cleaned dataset · {result.get('n_members')} members",
                f"Name: {name}",
                f"Saved under project datasets/",
                f"Path: {out}",
                f"Steps/plan: {result.get('n_steps')}",
                "",
                "Select this dataset in NeuroStudio → Data to train.",
            ]
            warn = result.get("warnings") or []
            if warn:
                lines.append("Warnings: " + "; ".join(str(w) for w in warn[:4]))
            _set_text(self._run_result, "\n".join(lines))
            self._run_status.setText(f"Saved as datasets/{name}")
            self._run_done = True
            # Keep selection on the cleaned output without leaving the Run stage.
            self._dataset_path = str(out)
            self._file_name.setText(name)
            self._file_badge.setText("DATASET")
            self._file_meta.setText(
                f"{result.get('n_members')} files · cleaned output"
            )
            self._file_path.setText(str(out))
            self._refresh_pickers()
            notify(
                "Dataset cleaned",
                f"{name} · {result.get('n_members')} files → datasets/{name}",
                level="success",
            )
            self._review_loaded = False
            self._refresh_actions()
            self.flow.go_to(REVIEW)
            return
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
        notify_library_changed()
        notify(
            "Run complete",
            f"{result.get('n_steps')} steps · {Path(str(out)).name}",
            level="success",
        )
        self._review_loaded = False
        self._refresh_pickers()
        self._refresh_actions()
        self.flow.go_to(REVIEW)

    def _resolve_preview_path(self) -> str:
        path = self._dataset_path
        if not path:
            return ""
        if is_dataset_manifest(path):
            try:
                manifest = load_manifest(path)
                if not manifest.members:
                    return ""
                return str(_fingerprint_member_path(manifest))
            except (OSError, ValueError):
                return ""
        return path

    def _load_inspect_preview(self) -> None:
        path = self._resolve_preview_path()
        if not path:
            self._inspect_status.setText("No recording to preview.")
            return
        if self._job and self._job.is_running():
            return
        self._inspect_path = path
        self._inspect_status.setText(f"Loading preview (first 30s)… {Path(path).name}")
        self._job_kind = "preview"
        job = preview_recording_job(path, max_sec=30.0, max_ch=16)
        start_bound_job(
            self,
            "_job",
            job,
            self._on_preview_ok,
            self._on_preview_fail,
            self._refresh_actions,
        )

    def _on_preview_ok(self, result: dict[str, Any]) -> None:
        import numpy as np

        data = result.get("data")
        if data is None:
            self._inspect_status.setText("Preview empty.")
            return
        arr = np.asarray(data, dtype=np.float32)
        events = [
            ViewerEvent(
                float(e["onset"]),
                float(e["duration"]),
                str(e["label"]),
                kind=str(e.get("kind") or "event"),
            )
            for e in (result.get("events") or [])
        ]
        ch_names = list(result.get("ch_names") or [])
        self._inspect_viewer.set_array(
            arr,
            sfreq=float(result.get("sfreq") or 100.0),
            ch_names=ch_names,
            events=events,
        )
        all_names = list(result.get("all_ch_names") or ch_names)
        self._inspect_channels.clear()
        bads = set(result.get("bads") or [])
        for name in all_names:
            item = QListWidgetItem(name)
            if name in bads:
                item.setText(f"{name} (bad)")
            self._inspect_channels.addItem(item)
        codes = sorted(
            {
                ev.label
                for ev in events
                if ev.kind != "bad" and not ev.label.upper().startswith("BAD")
            }
        )
        if codes and not self._inspect_labels.mapping():
            self._inspect_labels.set_codes(codes)
        self._inspect_status.setText(
            f"Preview ready · {arr.shape[0]} ch shown / {len(all_names)} total · "
            f"{float(result.get('duration_sec') or 0):.1f}s · "
            "Paint bad → drag spans · Save BAD marks · Drop channels as needed."
        )
        self._refresh_actions()

    def _on_preview_fail(self, code: str, message: str) -> None:
        self._inspect_status.setText(f"Preview failed ({code}): {message}")
        self._refresh_actions()

    def _on_bad_painted(self, tmin: float, tmax: float) -> None:
        self._pending_bads.append(
            {"onset": float(tmin), "duration": float(tmax - tmin)}
        )
        self._inspect_status.setText(
            f"{len(self._pending_bads)} BAD span(s) pending — click Save BAD marks."
        )

    def _save_inspect_bads(self) -> None:
        if not self._pending_bads or not self._inspect_path:
            return
        if self._job and self._job.is_running():
            return
        self._inspect_status.setText("Saving BAD annotations…")
        self._job_kind = "persist_bads"
        spans = list(self._pending_bads)
        job = persist_bad_spans_job(self._inspect_path, spans)
        start_bound_job(
            self,
            "_job",
            job,
            lambda result: self._on_bads_saved(result, len(spans)),
            lambda code, msg: self._inspect_status.setText(f"Save BAD failed: {msg}"),
            self._refresh_actions,
        )

    def _on_bads_saved(self, result: dict[str, Any], n: int) -> None:
        self._pending_bads.clear()
        if result.get("path"):
            self._inspect_path = str(result["path"])
        self._inspect_status.setText(f"Saved {n} BAD span(s) onto recording.")
        notify("BAD marks saved", f"{n} span(s)", level="success")
        self._load_inspect_preview()

    def _apply_inspect_montage(self) -> None:
        name = self._inspect_montage.currentData()
        if not name or not self._inspect_path:
            alert(self, "Montage", "Choose a montage and load a recording first.")
            return
        if self._job and self._job.is_running():
            return
        self._inspect_status.setText(f"Applying montage {name}…")
        self._job_kind = "montage"
        job = apply_montage_job(self._inspect_path, str(name))
        start_bound_job(
            self,
            "_job",
            job,
            lambda result: self._on_montage_applied(result),
            lambda code, msg: self._inspect_status.setText(f"Montage failed: {msg}"),
            self._refresh_actions,
        )

    def _on_montage_applied(self, result: dict[str, Any]) -> None:
        if result.get("path"):
            self._inspect_path = str(result["path"])
            # Prefer the FIF path for the rest of Flow when we converted.
            if not is_dataset_manifest(self._dataset_path):
                self._dataset_path = self._inspect_path
        self._inspect_status.setText(
            f"Montage applied: {result.get('montage') or '—'}"
        )
        notify("Montage applied", str(result.get("montage") or ""), level="success")
        self._load_inspect_preview()

    def _drop_inspect_channels(self) -> None:
        selected = [
            item.text().split(" ", 1)[0]
            for item in self._inspect_channels.selectedItems()
        ]
        if not selected or not self._inspect_path:
            return
        if self._job and self._job.is_running():
            return
        self._inspect_status.setText(f"Dropping {len(selected)} channel(s)…")
        self._job_kind = "drop_ch"
        job = drop_channels_job(self._inspect_path, selected)
        start_bound_job(
            self,
            "_job",
            job,
            lambda result: self._on_channels_dropped(result),
            lambda code, msg: self._inspect_status.setText(f"Drop failed: {msg}"),
            self._refresh_actions,
        )

    def _on_channels_dropped(self, result: dict[str, Any]) -> None:
        dropped = result.get("dropped") or []
        if result.get("path"):
            self._inspect_path = str(result["path"])
            if not is_dataset_manifest(self._dataset_path):
                self._dataset_path = self._inspect_path
        self._inspect_status.setText(f"Dropped {len(dropped)} channel(s).")
        notify("Channels dropped", ", ".join(dropped) or "—", level="success")
        self._load_inspect_preview()

    def _apply_inspect_prep(self) -> None:
        """Persist montage + label map onto dataset manifest when applicable."""
        if not is_dataset_manifest(self._dataset_path):
            return
        try:
            manifest = load_manifest(self._dataset_path)
        except (OSError, ValueError):
            return
        from neurotendrils.core.ingestion.schema import EventsConfig, MontageConfig
        from neurotendrils.core.dataset_manifest import save_manifest

        name = self._inspect_montage.currentData()
        manifest.montage = MontageConfig(name=str(name) if name else None)
        mapping = self._inspect_labels.mapping()
        if mapping:
            manifest.events = EventsConfig(source="manual", code_map=mapping)
            manifest.label.map = dict(mapping)
            manifest.label.class_names = self._inspect_labels.class_names()
        root = manifest.root_dir or Path(self._dataset_path).parent
        try:
            save_manifest(manifest, root)
        except OSError:
            return

    def _apply_review_ica_to_plan(self) -> bool:
        """Write exclude indices from the ICA browser into the plan's ICA step."""
        csv = self._ica_browser.exclude_csv()
        steps = self._plan.get("steps") or []
        for step in steps:
            if isinstance(step, dict) and step.get("step_id") == "ica":
                params = dict(step.get("params") or {})
                params["exclude"] = csv
                step["params"] = params
                self._plan_user_owned = True
                self.render_plan()
                return True
        return False

    def _on_apply_ica_clicked(self) -> None:
        if self._apply_review_ica_to_plan():
            notify(
                "ICA exclude saved",
                self._ica_browser.exclude_csv() or "(none)",
                level="success",
            )
            self._review_status.setText(
                "ICA exclude written into plan — re-run to apply, or continue to train."
            )
        else:
            alert(
                self,
                "No ICA step",
                "This plan has no ICA step to update. Add ICA in Plan, then re-run.",
            )

    def _load_review(self) -> None:
        """ICA / ERP / augment previews — always off the GUI thread."""
        out = self._run_output or ""
        path = Path(out)
        if is_dataset_manifest(out):
            try:
                manifest = load_manifest(out)
                path = resolve_member_path(manifest, manifest.members[0])
            except Exception:  # noqa: BLE001
                self._review_status.setText(
                    "Review: could not open cleaned dataset member."
                )
                return
        if self._job and self._job.is_running():
            return
        self._review_status.setText(f"Computing ICA / ERP / augment… {path.name}")
        self._job_kind = "review"
        job = review_qa_job(str(path))
        start_bound_job(
            self,
            "_job",
            job,
            self._on_review_ok,
            self._on_review_fail,
            self._refresh_actions,
        )

    def _on_review_ok(self, result: dict[str, Any]) -> None:
        if result.get("ica"):
            self._ica_browser.set_summary(result["ica"])
        if result.get("erp"):
            self._erp_plot.set_erp(result["erp"])
        if result.get("augment"):
            self._augment_review.set_preview(result["augment"])
        bits = []
        if result.get("ica"):
            bits.append("ICA")
        elif result.get("ica_error"):
            bits.append(f"ICA skipped ({result['ica_error'][:60]})")
        if result.get("erp"):
            bits.append("ERP")
        elif result.get("erp_error"):
            bits.append("ERP skipped")
        if result.get("augment"):
            bits.append("augment")
        self._review_status.setText(
            "Review ready · " + (" · ".join(bits) if bits else "no QA artifacts")
        )
        self._review_loaded = True
        self._refresh_actions()

    def _on_review_fail(self, code: str, message: str) -> None:
        self._review_status.setText(f"Review failed ({code}): {message}")
        self._refresh_actions()

    def _on_run_fail(self, code: str, message: str) -> None:
        self._run_skeleton.hide()
        self._cancel_btn.setVisible(False)
        if code == "cancelled":
            self._run_status.setText("Run cancelled.")
            notify("Run cancelled", level="info")
        else:
            self._run_status.setText(f"Run failed ({code}): {message}")
            notify("Run failed", message, level="error")
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

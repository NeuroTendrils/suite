"""NeuroStudio: data → template → tune → train → export, presented as a staged flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.dataset_actions import prompt_and_create_dataset
from neurotendrils.core.dataset_io import select_studio_path
from neurotendrils.core.dataset_manifest import (
    inspect_manifest_light,
    is_dataset_manifest,
    load_manifest,
)
from neurotendrils.core.eeg_formats import extension_badge, studio_file_filter
from neurotendrils.core.formatting import format_bytes
from neurotendrils.core.jobs import (
    WorkerJob,
    cancel_bound_job,
    export_job,
    infer_job,
    start_bound_job,
    train_job,
)
from neurotendrils.core.library import LibraryBus, notify_library_changed, scan_runs
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.core.studio_io import (
    default_config,
    ensure_model_hub_fields,
    find_template,
    latest_config_for,
    load_template_config,
    recommend,
    save_template_config,
    suggest_export_dir,
    suggest_infer_dir,
    suggest_train_dir,
    template_catalog,
    validate_config,
)
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.layoututil import clear_layout
from neurotendrils.widgets.modals import alert, edit_schema
from neurotendrils.widgets.motion import stagger_in
from neurotendrils.widgets.rows import ListRow, RowList
from neurotendrils.widgets.schema_form import SchemaFormWidget
from neurotendrils.widgets.section import SectionHeader
from neurotendrils.widgets.stage_flow import StageFlow
from neurotendrils.widgets.train_chart import TrainChart
from neurotendrils.core.notifications import notify

DATA = "data"
TEMPLATE = "template"
TUNE = "tune"
TRAIN = "train"
EXPORT = "export"
INFER = "infer"

_RECENT_LIMIT = 4


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


class _TemplateRow(QFrame):
    """Whole-row selectable template with an inline configure action."""

    activated = Signal()
    configureRequested = Signal()

    def __init__(
        self,
        title: str,
        meta: str,
        rationale: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("templateRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(2)
        self._title = QLabel(title, self)
        self._title.setObjectName("templateTitle")
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._meta = QLabel(meta, self)
        self._meta.setObjectName("templateMeta")
        self._meta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._rationale = QLabel(rationale, self)
        self._rationale.setObjectName("templateRationale")
        self._rationale.setWordWrap(True)
        self._rationale.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        text.addWidget(self._title)
        text.addWidget(self._meta)
        if rationale:
            text.addWidget(self._rationale)
        layout.addLayout(text, 1)

        self._badge = QLabel("", self)
        self._badge.setObjectName("fileBadge")
        self._badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._badge.hide()
        layout.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)

        configure = QPushButton("Configure", self)
        configure.setObjectName("planStepButton")
        configure.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        configure.setCursor(Qt.CursorShape.PointingHandCursor)
        configure.clicked.connect(self.configureRequested.emit)
        layout.addWidget(configure, 0, Qt.AlignmentFlag.AlignTop)

    def set_state(self, *, selected: bool, recommended: bool) -> None:
        name = "templateRowSelected" if selected else "templateRow"
        if self.objectName() != name:
            self.setObjectName(name)
            self.style().unpolish(self)
            self.style().polish(self)
        title_name = "templateTitleSelected" if selected else "templateTitle"
        if self._title.objectName() != title_name:
            self._title.setObjectName(title_name)
            self._title.style().unpolish(self._title)
            self._title.style().polish(self._title)
        if recommended:
            self._badge.setText("RECOMMENDED")
            self._badge.show()
        else:
            self._badge.hide()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class NeuroStudioPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dataset_path = ""
        self._selected_template = ""
        self._suggested_template = ""
        self._configs: dict[str, dict[str, Any]] = {}
        self._rationales: dict[str, str] = {}
        self._job: WorkerJob | None = None
        self._job_token = 0
        self._job_kind = ""
        self._template_pinned = False
        self._last_train: dict[str, Any] = {}
        self._train_log = ""
        self._catalog_cache: list[dict[str, Any]] | None = None
        self._export_done = False
        self._infer_done = False
        self._tune_valid = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.flow = StageFlow(
            "NeuroStudio",
            "Pick prepared data, choose a template, tune it, then train, export, and infer.",
            self,
        )
        self.flow.add_stage(DATA, "Data", self._build_dataset(), primary="Choose file")
        self.flow.add_stage(
            TEMPLATE, "Template", self._build_templates(), primary="Continue"
        )
        self.flow.add_stage(TUNE, "Tune", self._build_tune(), primary="Continue")
        self.flow.add_stage(TRAIN, "Train", self._build_train(), primary="Start training")
        self.flow.add_stage(EXPORT, "Export", self._build_export(), primary="Export")
        self.flow.add_stage(INFER, "Infer", self._build_infer(), primary="Run inference")
        self.flow.finalize()
        self.flow.primaryTriggered.connect(self._on_primary)
        self.flow.stageChanged.connect(lambda *_: self._refresh())
        layout.addWidget(self.flow)

        ProjectDir.instance().root_changed.connect(lambda *_: self._refresh_pickers())
        LibraryBus.instance().changed.connect(self._refresh_pickers)
        self._render_templates()
        self._refresh()

    # ---------- stages ----------

    def _build_dataset(self) -> QWidget:
        host, layout = _stage_widget(self)

        self._data_stack = QStackedWidget(host)
        empty = QFrame(host)
        empty.setObjectName("emptyPanel")
        el = QVBoxLayout(empty)
        el.setContentsMargins(20, 18, 20, 18)
        el.setSpacing(8)
        t = QLabel("No training data selected", empty)
        t.setObjectName("emptyPanelTitle")
        h = QLabel(
            "Create a multi-file dataset from lab sources (.set, .mat, .txt, …), "
            "or choose a single cleaned FIF / existing dataset.",
            empty,
        )
        h.setObjectName("emptyPanelHint")
        h.setWordWrap(True)
        choose = QPushButton("Browse file…", empty)
        choose.setObjectName("secondaryButton")
        choose.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        choose.setCursor(Qt.CursorShape.PointingHandCursor)
        choose.clicked.connect(self.choose_dataset)
        create = QPushButton("Create dataset…", empty)
        create.setObjectName("primaryButton")
        create.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        create.setCursor(Qt.CursorShape.PointingHandCursor)
        create.clicked.connect(self.create_dataset_from_files)
        open_ds = QPushButton("Open dataset…", empty)
        open_ds.setObjectName("secondaryButton")
        open_ds.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        open_ds.setCursor(Qt.CursorShape.PointingHandCursor)
        open_ds.clicked.connect(self.choose_dataset_manifest)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(create)
        btn_row.addWidget(open_ds)
        btn_row.addWidget(choose)
        btn_row.addStretch(1)
        el.addWidget(t)
        el.addWidget(h)
        el.addLayout(btn_row)

        selected = QFrame(host)
        selected.setObjectName("filePanel")
        sl = QVBoxLayout(selected)
        sl.setContentsMargins(20, 18, 20, 18)
        sl.setSpacing(6)
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
        change.clicked.connect(self.choose_dataset)
        clear = QPushButton("Clear", selected)
        clear.setObjectName("secondaryButton")
        clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        clear.clicked.connect(self.clear_dataset)
        btns.addWidget(change)
        btns.addWidget(clear)
        btns.addStretch(1)
        sl.addLayout(top)
        sl.addWidget(self._file_meta)
        sl.addWidget(self._file_path)
        sl.addSpacing(6)
        sl.addLayout(btns)

        self._data_stack.addWidget(empty)
        self._data_stack.addWidget(selected)
        layout.addWidget(self._data_stack)

        layout.addSpacing(16)
        header = SectionHeader("Recent run outputs", "Refresh", host)
        header.actionTriggered.connect(self._refresh_pickers)
        layout.addWidget(header)
        self._run_rows = RowList(host)
        layout.addWidget(self._run_rows)
        return host

    def _build_templates(self) -> QWidget:
        host, layout = _stage_widget(self)
        self._templates_status = QLabel(
            "Select training data to see recommendations.", host
        )
        self._templates_status.setObjectName("fileMetaLabel")
        rows_host = QWidget(host)
        self._template_list = QVBoxLayout(rows_host)
        self._template_list.setContentsMargins(0, 0, 0, 0)
        self._template_list.setSpacing(0)
        layout.addWidget(self._templates_status)
        layout.addWidget(rows_host)
        return host

    def _build_tune(self) -> QWidget:
        host, layout = _stage_widget(self)

        toolbar = QWidget(host)
        toolbar.setObjectName("stageToolbar")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self._tune_hint = QLabel("Select a template to tune it.", toolbar)
        self._tune_hint.setObjectName("fileMetaLabel")
        self._tune_save = QPushButton("Save", toolbar)
        self._tune_save.setObjectName("ghostButton")
        self._tune_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tune_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tune_save.clicked.connect(self.save_template_clicked)
        self._tune_load = QPushButton("Load", toolbar)
        self._tune_load.setObjectName("ghostButton")
        self._tune_load.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tune_load.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tune_load.clicked.connect(self.load_template_clicked)
        self._tune_reset = QPushButton("Reset", toolbar)
        self._tune_reset.setObjectName("ghostButton")
        self._tune_reset.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tune_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tune_reset.clicked.connect(self.reset_tune)
        row.addWidget(self._tune_hint, 1)
        row.addWidget(self._tune_save)
        row.addWidget(self._tune_load)
        row.addWidget(self._tune_reset)

        self._tune_form = SchemaFormWidget(host, columns=2)
        self._tune_form.values_changed.connect(self._on_tune_changed)
        self._tune_error = QLabel("", host)
        self._tune_error.setObjectName("stepEditError")
        self._tune_error.hide()

        layout.addWidget(toolbar)
        layout.addWidget(self._tune_form)
        layout.addWidget(self._tune_error)
        return host

    def _build_train(self) -> QWidget:
        host, layout = _stage_widget(self)

        split = QHBoxLayout()
        split.setSpacing(28)

        chart_col = QVBoxLayout()
        chart_col.setSpacing(12)
        self._train_chart = TrainChart(host)
        self._train_chart.setMinimumHeight(300)
        chart_col.addWidget(self._train_chart, 1)

        side = QWidget(host)
        side.setMinimumWidth(260)
        side.setMaximumWidth(360)
        side_l = QVBoxLayout(side)
        side_l.setContentsMargins(0, 0, 0, 0)
        side_l.setSpacing(12)

        device_row = QHBoxLayout()
        device_row.setSpacing(8)
        device_label = QLabel("Device", side)
        device_label.setObjectName("fileMetaLabel")
        self._device = QComboBox(side)
        self._device.addItems(["auto", "cpu", "cuda", "mps"])
        self._device.setMinimumWidth(120)
        device_row.addWidget(device_label)
        device_row.addWidget(self._device, 1)

        self._train_status = QLabel(
            "Ready to train when data and a template are set.", side
        )
        self._train_status.setObjectName("fileMetaLabel")
        self._train_status.setWordWrap(True)

        self._train_result = QLabel("", side)
        self._train_result.setObjectName("fileMetaLabel")
        self._train_result.setWordWrap(True)
        self._train_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._train_result.hide()

        self._train_log_label = QLabel("", side)
        self._train_log_label.setObjectName("fileMetaLabel")
        self._train_log_label.setWordWrap(True)
        self._train_log_label.hide()

        self._train_cancel = QPushButton("Cancel training", side)
        self._train_cancel.setObjectName("ghostButton")
        self._train_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._train_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._train_cancel.clicked.connect(self.cancel_job)
        self._train_cancel.hide()

        side_l.addLayout(device_row)
        side_l.addWidget(self._train_status)
        side_l.addWidget(self._train_result)
        side_l.addWidget(self._train_cancel, 0, Qt.AlignmentFlag.AlignLeft)
        side_l.addStretch(1)
        side_l.addWidget(self._train_log_label)

        split.addLayout(chart_col, 3)
        split.addWidget(side, 1)
        layout.addLayout(split, 1)
        return host

    def _build_export(self) -> QWidget:
        host, layout = _stage_widget(self)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(8)
        fmt_label = QLabel("Format", host)
        fmt_label.setObjectName("fileMetaLabel")
        self._export_format = QComboBox(host)
        self._export_format.addItems(["pt", "torchscript", "onnx", "safetensors"])
        self._export_format.setFixedWidth(140)
        fmt_row.addWidget(fmt_label)
        fmt_row.addWidget(self._export_format)
        fmt_row.addStretch(1)

        self._export_status = QLabel(
            "Export becomes available after a successful train.", host
        )
        self._export_status.setObjectName("fileMetaLabel")
        self._export_result = QLabel("", host)
        self._export_result.setObjectName("filePathLabel")
        self._export_result.setWordWrap(True)
        self._export_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._export_result.hide()

        layout.addLayout(fmt_row)
        layout.addWidget(self._export_status)
        layout.addWidget(self._export_result)
        return host

    def _build_infer(self) -> QWidget:
        host, layout = _stage_widget(self)
        self._infer_status = QLabel(
            "Run the trained checkpoint on the selected dataset or epochs.",
            host,
        )
        self._infer_status.setObjectName("fileMetaLabel")
        self._infer_status.setWordWrap(True)
        self._infer_result = QLabel("", host)
        self._infer_result.setObjectName("filePathLabel")
        self._infer_result.setWordWrap(True)
        self._infer_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._infer_result.hide()
        layout.addWidget(self._infer_status)
        layout.addWidget(self._infer_result)
        return host

    # ---------- flow chrome ----------

    def showEvent(self, event) -> None:  # noqa: ANN001, N802
        super().showEvent(event)
        self._refresh_pickers()

    def _refresh_pickers(self) -> None:
        self._run_rows.clear()
        runs = scan_runs()[:_RECENT_LIMIT]
        if not runs:
            self._run_rows.add_placeholder(
                "No runs yet. Run a plan in NeuroFlow first — cleaned.fif appears here."
            )
            return
        for entry in runs:
            output = str(entry.extra.get("output_path") or entry.path)
            row = ListRow(
                entry.title,
                entry.subtitle,
                format_bytes(entry.size_bytes),
                Glyph.RUNS,
                self._run_rows,
            )
            row.activated.connect(lambda path=output: self.set_dataset(path))
            self._run_rows.add_row(row)
        stagger_in(self._run_rows.rows())

    def _on_primary(self, key: str) -> None:
        if key == DATA:
            if not self._dataset_path:
                self.choose_dataset()
            else:
                self.flow.advance()
            return
        if key in {TEMPLATE, TUNE}:
            self.flow.advance()
            return
        if key == TRAIN:
            ckpt = self._last_train.get("checkpoint_path")
            if ckpt and not self._busy():
                self.flow.advance()
            else:
                self.start_training()
            return
        if key == EXPORT:
            if self._export_done:
                self.flow.go_to(INFER)
            else:
                self.start_export()
            return
        if key == INFER:
            self.start_inference()

    def _context_items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        if self._dataset_path:
            items.append(("Data", Path(self._dataset_path).name))
        if self._selected_template:
            tmpl = find_template(self._selected_template)
            items.append(
                ("Template", str(tmpl.get("title")) if tmpl else self._selected_template)
            )
        if self._dataset_path or self._selected_template:
            items.append(("Device", self._device.currentText()))
        metrics = self._last_train.get("metrics") or {}
        if metrics.get("accuracy") is not None:
            items.append(("Accuracy", str(metrics.get("accuracy"))))
        return items

    def _sync_flow(self) -> None:
        busy = self._busy()
        has_data = bool(self._dataset_path)
        has_template = bool(self._selected_template)
        ckpt = self._last_train.get("checkpoint_path")
        has_ckpt = bool(ckpt and Path(str(ckpt)).is_file())

        self.flow.set_complete(DATA, has_data)
        self.flow.set_complete(TEMPLATE, has_template)
        self.flow.set_complete(TUNE, has_template and self._tune_valid)
        self.flow.set_complete(TRAIN, has_ckpt)
        self.flow.set_complete(EXPORT, self._export_done)
        self.flow.set_complete(INFER, self._infer_done)

        self.flow.set_unlocked(TEMPLATE, has_data)
        self.flow.set_unlocked(TUNE, has_template)
        self.flow.set_unlocked(TRAIN, has_data and has_template)
        self.flow.set_unlocked(EXPORT, has_ckpt)
        self.flow.set_unlocked(INFER, has_ckpt)

        self.flow.set_context(self._context_items())

        stage = self.flow.current_key()
        if stage == DATA:
            self.flow.set_primary(
                "Continue" if has_data else "Choose file", enabled=not busy
            )
            self.flow.set_status("")
        elif stage == TEMPLATE:
            self.flow.set_primary("Continue", enabled=has_template)
            self.flow.set_status("")
        elif stage == TUNE:
            self.flow.set_primary("Continue", enabled=has_template and self._tune_valid)
            self.flow.set_status(self._tune_error.text() if not self._tune_valid else "")
        elif stage == TRAIN:
            training = busy and self._job_kind == "train"
            if training:
                self.flow.set_primary("Training…", enabled=False)
            elif has_ckpt:
                self.flow.set_primary("Continue", enabled=True)
            else:
                self.flow.set_primary(
                    "Start training", enabled=has_data and has_template and not busy
                )
            self.flow.set_status(self._train_status.text() if training else "")
        elif stage == INFER:
            inferring = busy and self._job_kind == "infer"
            if inferring:
                self.flow.set_primary("Inferring…", enabled=False)
            else:
                self.flow.set_primary(
                    "Run inference", enabled=has_ckpt and has_data and not busy
                )
            self.flow.set_status(self._infer_status.text() if inferring else "")
        else:
            exporting = busy and self._job_kind == "export"
            if exporting:
                self.flow.set_primary("Exporting…", enabled=False)
            elif self._export_done:
                self.flow.set_primary("Continue to Infer", enabled=True)
            else:
                self.flow.set_primary("Export", enabled=has_ckpt and not busy)
            self.flow.set_status(self._export_status.text() if exporting else "")

    # ---------- data ----------

    def choose_dataset(self) -> None:
        project = ProjectDir.instance()
        start = project.runs_dir()
        if not start.is_dir():
            start = project.datasets_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose training data",
            str(start),
            studio_file_filter(),
        )
        if not path:
            return
        self.set_dataset(path)

    def choose_dataset_manifest(self) -> None:
        project = ProjectDir.instance()
        start = project.datasets_dir()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open dataset manifest",
            str(start),
            "Dataset (dataset.json);;All files (*)",
        )
        if not path:
            return
        self.set_dataset(path)

    def create_dataset_from_files(self) -> None:
        self._job_kind = "dataset_ingest"
        self.flow.set_status("Importing dataset…")

        def _ok(result: dict[str, Any]) -> None:
            manifest = str(result.get("manifest_path") or "")
            if manifest:
                self.set_dataset(manifest)
            else:
                self.flow.set_status("")

        def _fail(_code: str, _message: str) -> None:
            self.flow.set_status("")

        started = prompt_and_create_dataset(
            self, self, on_ok=_ok, on_fail=_fail, after=self._refresh
        )
        if not started:
            self.flow.set_status("")
            self._job_kind = ""

    def set_dataset(self, path: str) -> None:
        if self._job is not None and self._job.is_running():
            alert(self, "Busy", "Wait for the current job to finish.")
            return
        try:
            resolved, kind = select_studio_path(path)
        except (OSError, ValueError, PermissionError) as exc:
            alert(self, "Invalid data", str(exc))
            return
        self._dataset_path = resolved
        self._export_done = False
        p = Path(resolved)
        if kind == "dataset_manifest" or is_dataset_manifest(resolved):
            try:
                manifest = load_manifest(resolved)
                summary = inspect_manifest_light(manifest)
            except (OSError, ValueError) as exc:
                alert(self, "Invalid dataset", str(exc))
                return
            self._file_name.setText(summary["name"])
            self._file_badge.setText("DATASET")
            hints = summary.get("filename_class_files") or {}
            hint_bit = (
                ", ".join(f"{k}×{v}" for k, v in sorted(hints.items()))
                if hints
                else summary.get("label_source")
            )
            warn_n = len(summary.get("warnings") or [])
            meta_parts = [
                f"{summary['n_members']} files",
                f"split {summary['split_mode']}",
                str(hint_bit),
            ]
            if summary.get("sfreq"):
                meta_parts.append(f"{summary['sfreq']} Hz")
            if warn_n:
                meta_parts.append(f"{warn_n} warnings")
            self._file_meta.setText(" · ".join(str(x) for x in meta_parts if x))
            self._file_path.setText(resolved)
            kind = "dataset_manifest"
        else:
            self._file_name.setText(p.name)
            self._file_badge.setText(extension_badge(resolved))
            self._file_meta.setText(f"{format_bytes(p.stat().st_size)} · {kind}")
            self._file_path.setText(resolved)
        self._data_stack.setCurrentIndex(1)
        self._suggested_template, self._rationales = recommend(resolved, kind)
        if not self._template_pinned or not self._selected_template:
            self.select_template(self._suggested_template, pinned=False)
        else:
            self._render_templates()
        self.flow.go_to(TEMPLATE)
        self._refresh()

    def clear_dataset(self) -> None:
        if self._job is not None and self._job.is_running():
            alert(self, "Busy", "Wait for the current job to finish.")
            return
        self.cancel_job()
        self._dataset_path = ""
        self._selected_template = ""
        self._suggested_template = ""
        self._template_pinned = False
        self._rationales = {}
        self._configs = {}
        self._last_train = {}
        self._train_log = ""
        self._export_done = False
        self._data_stack.setCurrentIndex(0)
        _set_text(self._train_result, "")
        _set_text(self._train_log_label, "")
        self._train_status.setText("Ready when data and a template are selected.")
        _set_text(self._export_result, "")
        self._export_status.setText("Export a trained checkpoint.")
        self._tune_form.set_schemas([], {})
        self._tune_hint.setText("Select a template to tune it.")
        self._templates_status.setText("Select training data to see recommendations.")
        self._render_templates()
        self.flow.go_to(DATA)
        self._refresh()

    # ---------- templates ----------

    def _render_templates(self) -> None:
        clear_layout(self._template_list)
        if self._catalog_cache is None:
            self._catalog_cache = template_catalog()
        rows: list[QWidget] = []
        for tmpl in self._catalog_cache:
            tid = tmpl["id"]
            row = _TemplateRow(
                tmpl["title"],
                f"{tmpl.get('task')} · {tmpl.get('model_family')}",
                self._rationales.get(tid, tmpl.get("description", "")),
            )
            row.set_state(
                selected=tid == self._selected_template,
                recommended=tid == self._suggested_template,
            )
            row.activated.connect(lambda i=tid: self.select_template(i))
            row.configureRequested.connect(lambda i=tid: self.configure_template(i))
            self._template_list.addWidget(row)
            rows.append(row)
        stagger_in(rows, gap=35)
        if self._dataset_path:
            suggested = find_template(self._suggested_template)
            label = suggested.get("title") if suggested else self._suggested_template
            self._templates_status.setText(f"Recommended: {label or '—'}")

    def select_template(self, template_id: str, *, pinned: bool = True) -> None:
        self._selected_template = template_id
        self._template_pinned = pinned
        if template_id not in self._configs:
            saved = latest_config_for(template_id)
            if saved and isinstance(saved.get("config"), dict):
                self._configs[template_id] = dict(saved["config"])
            else:
                self._configs[template_id] = default_config(template_id)
        tmpl = find_template(template_id)
        if tmpl:
            schemas = list(tmpl.get("hyperparams", [])) + list(tmpl.get("train", []))
            self._tune_form.set_schemas(schemas, self._configs[template_id])
            self._tune_hint.setText(f"Tuning {tmpl['title']}.")
        self._tune_valid = True
        self._tune_error.hide()
        self._render_templates()
        self._refresh()

    def configure_template(self, template_id: str) -> None:
        tmpl = find_template(template_id)
        if tmpl is None:
            return
        if template_id not in self._configs:
            self._configs[template_id] = default_config(template_id)
        schemas = list(tmpl.get("hyperparams", [])) + list(tmpl.get("train", []))
        values = edit_schema(
            self,
            f"Configure {tmpl['title']}",
            tmpl.get("description") or "",
            schemas,
            self._configs[template_id],
            lambda vals: validate_config(template_id, vals),
            decimals=6,
            single_step=0.0001,
        )
        if values is not None:
            self._configs[template_id] = values
            self.select_template(template_id)

    # ---------- tune ----------

    def _on_tune_changed(self, values: dict[str, Any]) -> None:
        if not self._selected_template:
            return
        self._configs[self._selected_template] = values
        err = validate_config(self._selected_template, values)
        self._tune_valid = not err
        if err:
            self._tune_error.setText(err)
            self._tune_error.show()
        else:
            self._tune_error.hide()
        self._sync_flow()

    def reset_tune(self) -> None:
        if not self._selected_template:
            return
        self._configs[self._selected_template] = default_config(self._selected_template)
        self.select_template(self._selected_template)

    def save_template_clicked(self) -> None:
        if not self._selected_template:
            return
        config = self._configs.get(self._selected_template) or default_config(
            self._selected_template
        )
        err = validate_config(self._selected_template, config)
        if err:
            alert(self, "Invalid config", err)
            return
        tmpl = find_template(self._selected_template)
        title = str(tmpl.get("title") if tmpl else self._selected_template)
        try:
            path = save_template_config(
                self._selected_template,
                config,
                name=title,
                dataset_path=self._dataset_path,
            )
        except (OSError, ValueError) as exc:
            alert(self, "Save failed", str(exc))
            return
        self._tune_hint.setText(f"Saved {path.name}")
        notify_library_changed()
        alert(self, "Template saved", str(path))

    def load_template_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load template",
            str(ProjectDir.instance().templates_dir()),
            "Templates (*.json)",
        )
        if not path:
            return
        try:
            payload = load_template_config(path)
        except (OSError, ValueError, PermissionError) as exc:
            alert(self, "Load failed", str(exc))
            return
        template_id = str(payload["template_id"])
        self._configs[template_id] = dict(payload["config"])
        self.select_template(template_id)
        name = str(payload.get("name") or Path(path).stem)
        self._tune_hint.setText(f"Loaded {name}")
        self.flow.go_to(TUNE)

    def apply_saved_template(self, path: str) -> None:
        """Open a project-saved template config (from Projects / Home)."""
        try:
            payload = load_template_config(path)
        except (OSError, ValueError, PermissionError) as exc:
            alert(self, "Load failed", str(exc))
            return
        template_id = str(payload["template_id"])
        self._configs[template_id] = dict(payload["config"])
        self.select_template(template_id)
        self.flow.go_to(TUNE)

    # ---------- train ----------

    def start_training(self) -> None:
        if not self._dataset_path or not self._selected_template:
            return
        if self._job and self._job.is_running():
            return
        config = self._configs.get(self._selected_template) or default_config(
            self._selected_template
        )
        err = validate_config(self._selected_template, config)
        if err:
            alert(self, "Invalid config", err)
            return
        try:
            out_dir = suggest_train_dir(self._dataset_path, self._selected_template)
        except OSError as exc:
            alert(self, "Train failed", str(exc))
            return
        # Persist the recipe used for this train so it survives app restarts.
        try:
            tmpl = find_template(self._selected_template)
            save_template_config(
                self._selected_template,
                config,
                name=str(tmpl.get("title") if tmpl else self._selected_template),
                dataset_path=self._dataset_path,
            )
            notify_library_changed()
        except (OSError, ValueError):
            pass
        self.flow.go_to(TRAIN)
        self._train_log = ""
        self._train_status.setText("Training…")
        self._train_chart.clear()
        _set_text(self._train_result, "")
        self._job_kind = "train"
        use_manifest = is_dataset_manifest(self._dataset_path)
        job = train_job(
            input_path="" if use_manifest else self._dataset_path,
            dataset_path=self._dataset_path if use_manifest else None,
            output_dir=str(out_dir),
            template_id=self._selected_template,
            config=config,
            device=self._device.currentText(),
        )
        job.progress.connect(self._on_train_progress)
        start_bound_job(
            self, "_job", job, self._on_train_ok, self._on_train_fail, self._refresh
        )

    def _on_train_progress(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or payload)
        if "epoch" in payload:
            total = payload.get("total_epochs", payload.get("epochs", "?"))
            loss = payload.get("loss")
            acc = payload.get("accuracy")
            val_loss = payload.get("val_loss")
            val_acc = payload.get("val_accuracy")
            message = f"Epoch {payload.get('epoch')}/{total}"
            extras = []
            if loss is not None:
                extras.append(f"loss {loss}")
            if acc is not None:
                extras.append(f"acc {acc}")
            if val_acc is not None:
                extras.append(f"val {val_acc}")
            if extras:
                message = f"{message}  ·  " + "  ·  ".join(str(x) for x in extras)
            try:
                self._train_chart.add_epoch(
                    int(payload.get("epoch") or 0),
                    loss=float(loss) if loss is not None else None,
                    accuracy=float(acc) if acc is not None else None,
                    val_loss=float(val_loss) if val_loss is not None else None,
                    val_accuracy=float(val_acc) if val_acc is not None else None,
                )
            except (TypeError, ValueError):
                pass
        self._train_status.setText(message)
        self.flow.set_status(message)
        # Keep a short rolling log for debugging; the chart is the primary view.
        self._train_log = (self._train_log + message + "\n")[-1200:]
        lines = [ln for ln in self._train_log.strip().splitlines() if ln][-6:]
        _set_text(self._train_log_label, "\n".join(lines))

    def _on_train_ok(self, result: dict[str, Any]) -> None:
        self._last_train = result
        ckpt = result.get("checkpoint_path", "")
        if ckpt and not ProjectDir.instance().contains(ckpt):
            self._train_status.setText("Train finished but checkpoint left the sandbox.")
            notify("Training finished", "Checkpoint left the project sandbox.", level="error")
            self._refresh()
            return
        metrics = result.get("metrics") or {}
        mode = result.get("data_mode", "?")
        ckpt_name = Path(str(ckpt)).name if ckpt else "—"
        run_dir = Path(str(ckpt)).parent.name if ckpt else ""
        _set_text(
            self._train_result,
            "\n".join(
                [
                    f"Mode  ·  {mode}",
                    f"Accuracy  ·  {metrics.get('accuracy')}",
                    f"Balanced  ·  {metrics.get('balanced_accuracy')}",
                    f"Checkpoint  ·  {ckpt_name}",
                    f"Run  ·  {run_dir}" if run_dir else "",
                ]
            ).strip(),
        )
        self._train_result.setToolTip(str(ckpt or ""))
        self._train_status.setText("Training complete.")
        stagger_in([self._train_result])
        notify_library_changed()
        notify(
            "Training complete",
            f"accuracy={metrics.get('accuracy')}  balanced={metrics.get('balanced_accuracy')}",
            level="success",
        )
        self._refresh()

    def _on_train_fail(self, code: str, message: str) -> None:
        if code == "cancelled":
            self._train_status.setText("Training cancelled.")
            notify("Training cancelled", level="info")
        else:
            self._train_status.setText(f"Train failed ({code}): {message}")
            notify("Training failed", message, level="error")
            if code == "no_labels":
                alert(self, "No labels", message)
        self._refresh()

    # ---------- export ----------

    def start_export(self) -> None:
        ckpt = self._last_train.get("checkpoint_path")
        if not ckpt or not Path(ckpt).is_file():
            return
        if self._job and self._job.is_running():
            return
        if self._last_train.get("data_mode") == "synthetic_demo":
            alert(
                self,
                "Export blocked",
                "This checkpoint was trained on synthetic demo data and cannot be exported.",
            )
            return
        fmt = self._export_format.currentText()
        out_dir = suggest_export_dir(self._selected_template, fmt)
        self.flow.go_to(EXPORT)
        self._export_status.setText("Exporting…")
        self._job_kind = "export"
        job = export_job(
            checkpoint_path=ckpt,
            output_dir=str(out_dir),
            format=fmt,
            train_meta_path=self._last_train.get("train_meta_path"),
        )
        start_bound_job(
            self,
            "_job",
            job,
            lambda result: self._on_export_ok(result, out_dir),
            self._on_export_fail,
            self._refresh,
        )

    def _on_export_ok(self, result: dict[str, Any], out_dir: Path) -> None:
        artifact = result.get("artifact_path") or result.get("output_path") or ""
        if artifact and not ProjectDir.instance().contains(artifact):
            self._export_status.setText("Export left the project sandbox.")
            notify("Export finished", "Artifact left the project sandbox.", level="error")
            return
        try:
            ensure_model_hub_fields(out_dir)
        except (OSError, PermissionError) as exc:
            self._export_status.setText(f"Export ok, Hub fields failed: {exc}")
            _set_text(self._export_result, f"Exported to {out_dir}\n{artifact}")
            notify("Export complete", str(exc), level="info")
            return
        _set_text(self._export_result, f"Exported to {out_dir}\n{artifact}")
        self._export_status.setText("Export complete.")
        self._export_done = True
        stagger_in([self._export_result])
        notify_library_changed()
        notify(
            "Export complete",
            Path(str(artifact or out_dir)).name,
            level="success",
        )
        self._refresh()

    def _on_export_fail(self, code: str, message: str) -> None:
        if code == "cancelled":
            self._export_status.setText("Export cancelled.")
            notify("Export cancelled", level="info")
        else:
            self._export_status.setText(f"Export failed ({code}): {message}")
            notify("Export failed", message, level="error")
        self._refresh()

    # ---------- infer ----------

    def start_inference(self) -> None:
        ckpt = self._last_train.get("checkpoint_path")
        if not ckpt or not Path(ckpt).is_file():
            alert(self, "No checkpoint", "Train a model before running inference.")
            return
        if not self._dataset_path:
            alert(self, "No data", "Choose a dataset or epochs file first.")
            return
        if self._job and self._job.is_running():
            return
        out_dir = suggest_infer_dir(self._selected_template or "infer")
        self.flow.go_to(INFER)
        self._infer_status.setText("Running inference…")
        self._infer_done = False
        self._job_kind = "infer"
        is_ds = is_dataset_manifest(self._dataset_path)
        job = infer_job(
            checkpoint_path=str(ckpt),
            output_dir=str(out_dir),
            input_path="" if is_ds else self._dataset_path,
            dataset_path=self._dataset_path if is_ds else None,
            device=self._device.currentText(),
        )
        start_bound_job(
            self,
            "_job",
            job,
            self._on_infer_ok,
            self._on_infer_fail,
            self._refresh,
        )

    def _on_infer_ok(self, result: dict[str, Any]) -> None:
        out = str(result.get("output_path") or "")
        metrics = result.get("metrics") or {}
        lines = [
            f"Inferred {result.get('n_trials')} trials",
            f"Output: {out}",
        ]
        if metrics.get("accuracy") is not None:
            lines.append(f"Accuracy vs labels: {metrics.get('accuracy')}")
        _set_text(self._infer_result, "\n".join(lines))
        self._infer_status.setText("Inference complete.")
        self._infer_done = True
        notify_library_changed()
        notify(
            "Inference complete",
            f"{result.get('n_trials')} trials → {Path(out).name}",
            level="success",
        )
        self._refresh()

    def _on_infer_fail(self, code: str, message: str) -> None:
        if code == "cancelled":
            self._infer_status.setText("Inference cancelled.")
            notify("Inference cancelled", level="info")
        else:
            self._infer_status.setText(f"Inference failed ({code}): {message}")
            notify("Inference failed", message, level="error")
        self._refresh()

    # ---------- shared ----------

    def _busy(self) -> bool:
        return self._job is not None and self._job.is_running()

    def cancel_job(self) -> None:
        if self._job is None or not self._job.is_running():
            return
        kind = self._job_kind
        if cancel_bound_job(self, "_job"):
            if kind == "export":
                self._export_status.setText("Cancelling…")
            else:
                self._train_status.setText("Cancelling…")
            self._refresh()

    def _refresh(self) -> None:
        busy = self._busy()
        self._train_cancel.setVisible(busy and self._job_kind == "train")
        has_template = bool(self._selected_template)
        self._tune_reset.setEnabled(has_template and not busy)
        self._tune_save.setEnabled(has_template and not busy)
        self._tune_load.setEnabled(not busy)
        self._sync_flow()

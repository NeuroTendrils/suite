"""NeuroStudio page: dataset → templates → tune → train → export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.dataset_io import select_studio_path
from neurotendrils.core.eeg_formats import extension_badge, studio_file_filter
from neurotendrils.core.formatting import format_bytes
from neurotendrils.core.jobs import (
    WorkerJob,
    cancel_bound_job,
    export_job,
    start_bound_job,
    train_job,
)
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.core.studio_io import (
    default_config,
    ensure_model_hub_fields,
    find_template,
    recommend,
    suggest_export_dir,
    suggest_train_dir,
    template_catalog,
    validate_config,
)
from neurotendrils.widgets.layoututil import clear_layout
from neurotendrils.widgets.pageheader import PageHeader
from neurotendrils.widgets.schema_form import SchemaEditDialog, SchemaFormWidget
from neurotendrils.widgets.scroll_page import ScrollPage
from neurotendrils.widgets.skeleton import SkeletonLoader


class NeuroStudioPage(ScrollPage):
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

        self.content_layout.addWidget(
            PageHeader(
                "NeuroStudio",
                "Train template models locally on cleaned EEG, then export.",
            )
        )
        self._build_dataset()
        self._build_templates()
        self._build_tune()
        self._build_train()
        self._build_export()
        self.content_layout.addStretch(1)
        self._refresh()

    def _build_dataset(self) -> None:
        self.content_layout.addWidget(self.section_label("Training data"))
        self._data_stack = QStackedWidget(self)
        empty = QFrame(self)
        empty.setObjectName("emptyPanel")
        el = QVBoxLayout(empty)
        t = QLabel("No training data selected", empty)
        t.setObjectName("emptyPanelTitle")
        h = QLabel(
            "Choose a Flow run output (cleaned.fif) or a dataset inside the project.",
            empty,
        )
        h.setObjectName("emptyPanelHint")
        h.setWordWrap(True)
        choose = QPushButton("Choose file", empty)
        choose.setObjectName("primaryButton")
        choose.clicked.connect(self.choose_dataset)
        el.addWidget(t)
        el.addWidget(h)
        el.addWidget(choose, alignment=Qt.AlignmentFlag.AlignLeft)

        selected = QFrame(self)
        selected.setObjectName("filePanel")
        sl = QVBoxLayout(selected)
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
        change.clicked.connect(self.choose_dataset)
        clear = QPushButton("Clear", selected)
        clear.setObjectName("secondaryButton")
        clear.clicked.connect(self.clear_dataset)
        btns.addWidget(change)
        btns.addWidget(clear)
        btns.addStretch(1)
        sl.addLayout(top)
        sl.addWidget(self._file_meta)
        sl.addWidget(self._file_path)
        sl.addLayout(btns)
        self._data_stack.addWidget(empty)
        self._data_stack.addWidget(selected)
        self.content_layout.addWidget(self._data_stack)

    def _build_templates(self) -> None:
        self.content_layout.addWidget(self.section_label("Templates"))
        self._templates_status = QLabel("Select training data to see recommendations.", self)
        self._templates_status.setObjectName("fileMetaLabel")
        self._template_list = QVBoxLayout()
        self._template_list.setSpacing(8)
        host = QWidget(self)
        host.setLayout(self._template_list)
        self.content_layout.addWidget(self._templates_status)
        self.content_layout.addWidget(host)
        self._render_templates()

    def _build_tune(self) -> None:
        self.content_layout.addWidget(self.section_label("Tune"))
        self._tune_form = SchemaFormWidget(self)
        self._tune_form.values_changed.connect(self._on_tune_changed)
        self._tune_error = QLabel("", self)
        self._tune_error.setObjectName("stepEditError")
        self._tune_error.hide()
        reset = QPushButton("Reset to defaults", self)
        reset.setObjectName("secondaryButton")
        reset.clicked.connect(self.reset_tune)
        self.content_layout.addWidget(self._tune_form)
        self.content_layout.addWidget(self._tune_error)
        self.content_layout.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)

    def _build_train(self) -> None:
        self.content_layout.addWidget(self.section_label("Train"))
        device_row = QHBoxLayout()
        device_row.addWidget(QLabel("Device", self))
        self._device = QComboBox(self)
        self._device.addItems(["auto", "cpu", "cuda", "mps"])
        device_row.addWidget(self._device)
        device_row.addStretch(1)
        self._train_status = QLabel("Select a template to train.", self)
        self._train_status.setObjectName("fileMetaLabel")
        self._train_skeleton = SkeletonLoader(self)
        self._train_skeleton.hide()
        self._train_result = QLabel("", self)
        self._train_result.setObjectName("filePathLabel")
        self._train_result.setWordWrap(True)
        self._train_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._train_log_label = QLabel("", self)
        self._train_log_label.setObjectName("fileMetaLabel")
        self._train_log_label.setWordWrap(True)
        row = QHBoxLayout()
        self._train_btn = QPushButton("Train")
        self._train_btn.setObjectName("primaryButton")
        self._train_btn.clicked.connect(self.start_training)
        self._train_cancel = QPushButton("Cancel")
        self._train_cancel.setObjectName("secondaryButton")
        self._train_cancel.clicked.connect(self.cancel_job)
        row.addWidget(self._train_btn)
        row.addWidget(self._train_cancel)
        row.addStretch(1)
        self.content_layout.addLayout(device_row)
        self.content_layout.addWidget(self._train_status)
        self.content_layout.addWidget(self._train_skeleton)
        self.content_layout.addWidget(self._train_result)
        self.content_layout.addWidget(self._train_log_label)
        self.content_layout.addLayout(row)

    def _build_export(self) -> None:
        self.content_layout.addWidget(self.section_label("Export"))
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format", self))
        self._export_format = QComboBox(self)
        self._export_format.addItems(["pt", "torchscript", "onnx", "safetensors"])
        fmt_row.addWidget(self._export_format)
        fmt_row.addStretch(1)
        self._export_status = QLabel("Export becomes available after a successful train.", self)
        self._export_status.setObjectName("fileMetaLabel")
        self._export_result = QLabel("", self)
        self._export_result.setObjectName("filePathLabel")
        self._export_result.setWordWrap(True)
        self._export_result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        self._export_btn = QPushButton("Export")
        self._export_btn.setObjectName("primaryButton")
        self._export_btn.clicked.connect(self.start_export)
        publish = QPushButton("Publish to Hub")
        publish.setObjectName("secondaryButton")
        publish.setEnabled(False)
        publish.setToolTip("Cloud publish comes with NeuroTendrils Hub.")
        row.addWidget(self._export_btn)
        row.addWidget(publish)
        row.addStretch(1)
        self.content_layout.addLayout(fmt_row)
        self.content_layout.addWidget(self._export_status)
        self.content_layout.addWidget(self._export_result)
        self.content_layout.addLayout(row)

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
        if self._job is not None and self._job.is_running():
            QMessageBox.information(self, "Busy", "Wait for the current job to finish.")
            return
        try:
            resolved, kind = select_studio_path(path)
        except (OSError, ValueError, PermissionError) as exc:
            QMessageBox.warning(self, "Invalid data", str(exc))
            return
        self._dataset_path = resolved
        p = Path(resolved)
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
        self._refresh()

    def clear_dataset(self) -> None:
        if self._job is not None and self._job.is_running():
            QMessageBox.information(self, "Busy", "Wait for the current job to finish.")
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
        self._data_stack.setCurrentIndex(0)
        self._train_result.clear()
        self._train_log_label.clear()
        self._train_status.setText("Ready when data and a template are selected.")
        self._export_result.clear()
        self._export_status.setText("Export a trained checkpoint.")
        self._tune_form.set_schemas([], {})
        self._templates_status.setText("Select training data to see recommendations.")
        self._render_templates()
        self._refresh()

    def _render_templates(self) -> None:
        clear_layout(self._template_list)
        if self._catalog_cache is None:
            self._catalog_cache = template_catalog()
        for tmpl in self._catalog_cache:
            tid = tmpl["id"]
            row = QFrame(self)
            row.setObjectName("templateRow")
            layout = QHBoxLayout(row)
            text = QVBoxLayout()
            title = QLabel(tmpl["title"], row)
            title.setObjectName("templateTitle")
            marks = []
            if tid == self._selected_template:
                marks.append("selected")
            if tid == self._suggested_template:
                marks.append("recommended")
            meta = QLabel(
                f"{tmpl.get('task')} · {tmpl.get('model_family')}"
                + (f" · {', '.join(marks)}" if marks else ""),
                row,
            )
            meta.setObjectName("templateMeta")
            rationale = QLabel(self._rationales.get(tid, tmpl.get("description", "")), row)
            rationale.setObjectName("templateRationale")
            rationale.setWordWrap(True)
            text.addWidget(title)
            text.addWidget(meta)
            text.addWidget(rationale)
            btns = QVBoxLayout()
            select = QPushButton("Select", row)
            select.setObjectName("planStepButton")
            select.clicked.connect(lambda _=False, i=tid: self.select_template(i))
            configure = QPushButton("Configure", row)
            configure.setObjectName("planStepButton")
            configure.clicked.connect(lambda _=False, i=tid: self.configure_template(i))
            btns.addWidget(select)
            btns.addWidget(configure)
            layout.addLayout(text, 1)
            layout.addLayout(btns)
            self._template_list.addWidget(row)
        if self._dataset_path:
            self._templates_status.setText(
                f"Suggested: {self._suggested_template or '—'}"
            )

    def select_template(self, template_id: str, *, pinned: bool = True) -> None:
        self._selected_template = template_id
        self._template_pinned = pinned
        if template_id not in self._configs:
            self._configs[template_id] = default_config(template_id)
        tmpl = find_template(template_id)
        if tmpl:
            schemas = list(tmpl.get("hyperparams", [])) + list(tmpl.get("train", []))
            self._tune_form.set_schemas(schemas, self._configs[template_id])
        self._render_templates()
        self._refresh()

    def configure_template(self, template_id: str) -> None:
        tmpl = find_template(template_id)
        if tmpl is None:
            return
        if template_id not in self._configs:
            self._configs[template_id] = default_config(template_id)
        schemas = list(tmpl.get("hyperparams", [])) + list(tmpl.get("train", []))
        dialog = SchemaEditDialog(
            f"Configure {tmpl['title']}",
            tmpl.get("description") or "",
            schemas,
            self._configs[template_id],
            lambda values: validate_config(template_id, values),
            self,
            decimals=6,
            single_step=0.0001,
        )
        if dialog.exec():
            self._configs[template_id] = dialog.values()
            self.select_template(template_id)

    def _on_tune_changed(self, values: dict[str, Any]) -> None:
        if not self._selected_template:
            return
        self._configs[self._selected_template] = values
        err = validate_config(self._selected_template, values)
        if err:
            self._tune_error.setText(err)
            self._tune_error.show()
        else:
            self._tune_error.hide()

    def reset_tune(self) -> None:
        if not self._selected_template:
            return
        self._configs[self._selected_template] = default_config(self._selected_template)
        self.select_template(self._selected_template)

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
            QMessageBox.warning(self, "Invalid config", err)
            return
        try:
            out_dir = suggest_train_dir(self._dataset_path, self._selected_template)
        except OSError as exc:
            QMessageBox.warning(self, "Train failed", str(exc))
            return
        self._train_log = ""
        self._train_status.setText("Training…")
        self._train_skeleton.show()
        self._train_result.clear()
        self._job_kind = "train"
        job = train_job(
            input_path=self._dataset_path,
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
            message = (
                f"epoch {payload.get('epoch')}/{total}  "
                f"loss={payload.get('loss')}  acc={payload.get('accuracy')}"
            )
        self._train_status.setText(message)
        self._train_log = (self._train_log + message + "\n")[-4000:]
        self._train_log_label.setText(self._train_log.strip())

    def _on_train_ok(self, result: dict[str, Any]) -> None:
        self._train_skeleton.hide()
        self._last_train = result
        ckpt = result.get("checkpoint_path", "")
        if ckpt and not ProjectDir.instance().contains(ckpt):
            self._train_status.setText("Train finished but checkpoint left the sandbox.")
            self._refresh()
            return
        metrics = result.get("metrics") or {}
        mode = result.get("data_mode", "?")
        self._train_result.setText(
            "\n".join(
                [
                    f"data_mode={mode}",
                    f"accuracy={metrics.get('accuracy')}  "
                    f"balanced={metrics.get('balanced_accuracy')}",
                    f"checkpoint: {ckpt}",
                    f"metrics: {result.get('metrics_path')}",
                    f"train meta: {result.get('train_meta_path')}",
                ]
            )
        )
        self._train_status.setText("Training complete.")
        self._refresh()

    def _on_train_fail(self, code: str, message: str) -> None:
        self._train_skeleton.hide()
        if code == "cancelled":
            self._train_status.setText("Training cancelled.")
        else:
            self._train_status.setText(f"Train failed ({code}): {message}")
            if code == "no_labels":
                QMessageBox.warning(self, "No labels", message)
        self._refresh()

    def start_export(self) -> None:
        ckpt = self._last_train.get("checkpoint_path")
        if not ckpt or not Path(ckpt).is_file():
            return
        if self._job and self._job.is_running():
            return
        if self._last_train.get("data_mode") == "synthetic_demo":
            QMessageBox.warning(
                self,
                "Export blocked",
                "This checkpoint was trained on synthetic demo data and cannot be exported.",
            )
            return
        fmt = self._export_format.currentText()
        out_dir = suggest_export_dir(self._selected_template, fmt)
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
            return
        try:
            ensure_model_hub_fields(out_dir)
        except (OSError, PermissionError) as exc:
            self._export_status.setText(f"Export ok, Hub fields failed: {exc}")
            self._export_result.setText(f"Exported to {out_dir}\n{artifact}")
            return
        self._export_result.setText(f"Exported to {out_dir}\n{artifact}")
        self._export_status.setText("Export complete.")
        self._refresh()

    def _on_export_fail(self, code: str, message: str) -> None:
        if code == "cancelled":
            self._export_status.setText("Export cancelled.")
        else:
            self._export_status.setText(f"Export failed ({code}): {message}")
        self._refresh()

    def cancel_job(self) -> None:
        if self._job is None or not self._job.is_running():
            return
        kind = self._job_kind
        if cancel_bound_job(self, "_job"):
            if kind == "export":
                self._export_status.setText("Cancelling…")
            else:
                self._train_skeleton.hide()
                self._train_status.setText("Cancelling…")
            self._refresh()

    def _refresh(self) -> None:
        busy = self._job is not None and self._job.is_running()
        self._train_btn.setEnabled(
            bool(self._dataset_path and self._selected_template) and not busy
        )
        self._train_cancel.setEnabled(busy)
        ckpt = self._last_train.get("checkpoint_path")
        self._export_btn.setEnabled(bool(ckpt and Path(str(ckpt)).is_file()) and not busy)

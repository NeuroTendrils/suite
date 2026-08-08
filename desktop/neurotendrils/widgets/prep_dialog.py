"""Manual prep dialog: viewer, montage, labels, about — then save onto dataset/recording."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.dataset_manifest import (
    is_dataset_manifest,
    load_manifest,
    resolve_member_path,
    save_manifest,
)
from neurotendrils.core.ingestion.montage import STANDARD_MONTAGES
from neurotendrils.core.ingestion.schema import (
    AboutInfo,
    EventsConfig,
    MontageConfig,
)
from neurotendrils.core.library import notify_library_changed
from neurotendrils.core.notifications import notify
from neurotendrils.widgets import modals
from neurotendrils.widgets.eeg_viewer import EegViewer
from neurotendrils.widgets.trial_labels import AboutEditor, TrialLabelEditor


class PrepPanel(QWidget):
    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = Path(path)
        self._manifest = None
        self._member_path: Path | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(10)

        title = QLabel("Prepare recording", self)
        title.setObjectName("inspectorTitle")
        root.addWidget(title)
        self._subtitle = QLabel(self._path.name, self)
        self._subtitle.setObjectName("mutedLabel")
        self._subtitle.setWordWrap(True)
        root.addWidget(self._subtitle)

        tabs = QTabWidget(self)
        # Viewer
        viewer_page = QWidget(tabs)
        viewer_layout = QVBoxLayout(viewer_page)
        viewer_layout.setContentsMargins(0, 8, 0, 0)
        self._viewer = EegViewer(viewer_page)
        viewer_layout.addWidget(self._viewer, 1)
        tabs.addTab(viewer_page, "Viewer")

        # Montage + about
        meta_page = QWidget(tabs)
        meta_layout = QVBoxLayout(meta_page)
        meta_layout.setContentsMargins(0, 8, 0, 0)
        form = QFormLayout()
        self._montage = QComboBox(meta_page)
        self._montage.addItem("(none)", None)
        for name in STANDARD_MONTAGES:
            self._montage.addItem(name, name)
        form.addRow("Montage", self._montage)
        meta_layout.addLayout(form)
        self._about = AboutEditor(meta_page)
        meta_layout.addWidget(self._about)
        meta_layout.addStretch(1)
        tabs.addTab(meta_page, "About / montage")

        # Labels
        labels_page = QWidget(tabs)
        labels_layout = QVBoxLayout(labels_page)
        labels_layout.setContentsMargins(0, 8, 0, 0)
        self._labels = TrialLabelEditor(labels_page)
        labels_layout.addWidget(self._labels, 1)
        tabs.addTab(labels_page, "Labels")

        root.addWidget(tabs, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self._cancel)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        root.addLayout(row)

        self._load()

    def _load(self) -> None:
        path = self._path
        preview_path: Path | None = None
        if is_dataset_manifest(path):
            try:
                self._manifest = load_manifest(path)
            except (OSError, ValueError) as exc:
                self._subtitle.setText(f"Could not load dataset: {exc}")
                return
            self._subtitle.setText(
                f"{self._manifest.name} · {len(self._manifest.members)} members"
            )
            # Prefill editors from manifest
            about = self._manifest.about
            self._about.set_about(about.summary, about.tags, about.notes)
            if self._manifest.montage.name:
                idx = self._montage.findData(self._manifest.montage.name)
                if idx >= 0:
                    self._montage.setCurrentIndex(idx)
            mapping = dict(self._manifest.events.code_map) or dict(
                self._manifest.label.map
            )
            if mapping:
                self._labels.set_mapping(mapping)
            if self._manifest.members:
                try:
                    preview_path = resolve_member_path(
                        self._manifest, self._manifest.members[0]
                    )
                    self._member_path = preview_path
                except OSError:
                    preview_path = None
        else:
            preview_path = path

        if preview_path is not None:
            err = self._viewer.load_path(str(preview_path))
            if err:
                self._subtitle.setText(err)
            else:
                # Seed label rows from annotation labels found in the viewer events.
                codes = sorted(
                    {
                        ev.label
                        for ev in self._viewer.events()
                        if ev.kind != "bad" and not ev.label.upper().startswith("BAD")
                    }
                )
                if codes and not self._labels.mapping():
                    self._labels.set_codes(codes)

    def _save(self) -> None:
        montage_name = self._montage.currentData()
        about_raw = self._about.about_dict()
        about = AboutInfo.from_dict(
            {
                "summary": str(about_raw.get("summary") or ""),
                "tags": list(about_raw.get("tags") or []),
                "notes": str(about_raw.get("notes") or ""),
            }
        )
        mapping = self._labels.mapping()
        events = EventsConfig(source="manual", code_map=mapping)

        if self._manifest is not None:
            self._manifest.about = about
            self._manifest.montage = MontageConfig(
                name=str(montage_name) if montage_name else None
            )
            self._manifest.events = events
            if mapping:
                self._manifest.label.map = dict(mapping)
                self._manifest.label.class_names = self._labels.class_names()
            root = self._manifest.root_dir or self._path.parent
            try:
                save_manifest(self._manifest, root)
            except OSError as exc:
                modals.alert(self, "Save failed", str(exc))
                return
            # Persist bad spans onto the previewed member FIF when possible.
            self._persist_bad_annotations()
            notify_library_changed()
            notify("Prepared", self._manifest.name, level="info")
        else:
            # Single-file: write a sidecar prep.json next to the recording.
            sidecar = self._path.with_suffix(self._path.suffix + ".prep.json")
            import json

            payload = {
                "about": about.to_dict(),
                "montage": {"name": montage_name, "custom_path": None},
                "events": events.to_dict(),
            }
            try:
                sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except OSError as exc:
                modals.alert(self, "Save failed", str(exc))
                return
            self._persist_bad_annotations()
            notify_library_changed()
            notify("Prepared", self._path.name, level="info")

        host = modals.find_host(self)
        if host is not None:
            host.dismiss()

    def _persist_bad_annotations(self) -> None:
        target = self._member_path or (
            self._path if self._path.is_file() else None
        )
        if target is None or not target.is_file():
            return
        bads = [ev for ev in self._viewer.events() if ev.kind == "bad"]
        if not bads:
            return
        try:
            from neurotendrils.core.ingestion.readers import read_recording
            import mne

            raw = read_recording(target, preload=True)
            if isinstance(raw, mne.Epochs):
                return
            onsets = list(raw.annotations.onset) if raw.annotations else []
            durations = list(raw.annotations.duration) if raw.annotations else []
            descs = list(raw.annotations.description) if raw.annotations else []
            for ev in bads:
                onsets.append(ev.onset)
                durations.append(ev.duration)
                descs.append("BAD")
            raw.set_annotations(
                mne.Annotations(onset=onsets, duration=durations, description=descs)
            )
            # Prefer FIF write; for non-FIF leave sidecar-only.
            if target.suffix.lower() in {".fif"} or target.name.endswith(".fif.gz"):
                raw.save(str(target), overwrite=True, verbose="ERROR")
        except Exception:  # noqa: BLE001
            # Prep metadata still saved; bad paint persistence is best-effort.
            return

    def _cancel(self) -> None:
        host = modals.find_host(self)
        if host is not None:
            host.dismiss()


def open_prep_dialog(anchor: QWidget, path: str) -> None:
    panel = PrepPanel(path, anchor)
    modals.present(anchor, panel, max_width=960, max_height=720, dismissible=True)

"""Compact EEGLAB-like plot panel (channel layout, spectra, ERP, ICA)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.widgets.erp_image import ErpImage
from neurotendrils.widgets.erp_plot import ErpPlot
from neurotendrils.widgets.ica_maps import IcaMapBrowser
from neurotendrils.widgets.spectra_plot import SpectraPlot
from neurotendrils.widgets.topoplot import TopoPlot, positions_on_circle


class PlotHub(QWidget):
    """Tabbed plot panel for NeuroTendrils inspection / prep workflows."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget(self)
        root.addWidget(self._tabs, 1)

        # Channel locations
        ch_page = QWidget(self._tabs)
        ch_layout = QVBoxLayout(ch_page)
        ch_layout.setContentsMargins(0, 8, 0, 0)
        ch_hint = QLabel("Electrode layout (flat positions)", ch_page)
        ch_hint.setObjectName("mutedLabel")
        ch_layout.addWidget(ch_hint)
        ch_scroll = QScrollArea(ch_page)
        ch_scroll.setWidgetResizable(True)
        ch_body = QWidget(ch_scroll)
        self._ch_grid = QGridLayout(ch_body)
        self._ch_grid.setContentsMargins(0, 0, 0, 0)
        self._ch_grid.setSpacing(6)
        ch_scroll.setWidget(ch_body)
        ch_layout.addWidget(ch_scroll, 1)
        self._ch_names: list[str] = []
        self._positions: list[tuple[float, float]] = []
        self._ch_topos: list[TopoPlot] = []
        self._tabs.addTab(ch_page, "Channels")

        # Spectra
        self._spectra = SpectraPlot(self._tabs)
        self._tabs.addTab(self._spectra, "Spectra")

        # ERP
        self._erp = ErpPlot(self._tabs)
        self._tabs.addTab(self._erp, "ERP")

        # ERP image
        self._erp_image = ErpImage(self._tabs)
        self._tabs.addTab(self._erp_image, "ERP image")

        # ICA maps
        self._ica = IcaMapBrowser(self._tabs)
        self._tabs.addTab(self._ica, "ICA maps")

    def set_channel_positions(
        self,
        ch_names: list[str],
        positions: list[tuple[float, float]] | None = None,
    ) -> None:
        self._ch_names = [str(n) for n in ch_names]
        if positions is not None and len(positions) >= len(self._ch_names):
            self._positions = [(float(p[0]), float(p[1])) for p in positions]
        else:
            self._positions = positions_on_circle(len(self._ch_names))
        self._rebuild_channel_grid()

    def _rebuild_channel_grid(self) -> None:
        while self._ch_grid.count():
            item = self._ch_grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._ch_topos.clear()

        if not self._ch_names:
            empty = QLabel("No channel positions", self)
            empty.setObjectName("mutedLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._ch_grid.addWidget(empty, 0, 0)
            return

        # Single overview topo with zeros + label strip
        overview = TopoPlot()
        overview.setMinimumSize(160, 160)
        zeros = [0.0] * len(self._ch_names)
        overview.set_map(zeros, self._ch_names, self._positions)
        overview.set_title(f"{len(self._ch_names)} channels")
        self._ch_grid.addWidget(overview, 0, 0, 1, 2)
        self._ch_topos.append(overview)

        # Compact name grid
        cols = 4
        for i, name in enumerate(self._ch_names):
            row = 1 + i // cols
            col = i % cols
            cell = QWidget()
            row_layout = QHBoxLayout(cell)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            mini = TopoPlot(cell)
            mini.setFixedSize(48, 48)
            mini.set_map([0.0], [name], [self._positions[i]] if i < len(self._positions) else None)
            row_layout.addWidget(mini)
            lbl = QLabel(name, cell)
            lbl.setObjectName("rowMono")
            row_layout.addWidget(lbl, 1)
            self._ch_grid.addWidget(cell, row, col)
            self._ch_topos.append(mini)

    def set_spectra(self, freqs: list[float], channels: dict[str, list[float]]) -> None:
        self._spectra.set_spectra(freqs, channels)

    def set_erp(self, payload: dict) -> None:
        self._erp.set_erp(payload)

    def set_erp_image(
        self,
        trials: list[list[float]],
        times: list[float],
        *,
        title: str = "",
    ) -> None:
        self._erp_image.set_data(trials, times, title=title)

    def set_ica(self, summary: dict) -> None:
        self._ica.set_summary(summary)

    def ica_browser(self) -> IcaMapBrowser:
        return self._ica

    def show_tab(self, name: str) -> None:
        labels = ["Channels", "Spectra", "ERP", "ERP image", "ICA maps"]
        key = name.strip().lower()
        for i, label in enumerate(labels):
            if label.lower() == key or key in label.lower():
                self._tabs.setCurrentIndex(i)
                return

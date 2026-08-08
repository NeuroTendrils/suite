"""EEGLAB-style 2D ERP map series (topo at successive latencies)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from neurotendrils.widgets.topoplot import TopoPlot, positions_on_circle


class ErpMapSeries(QWidget):
    """Grid of scalp maps at evenly spaced times through an ERP average."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        self._title = QLabel("ERP map series", self)
        self._title.setObjectName("sectionLabel")
        root.addWidget(self._title)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        self._grid = QGridLayout(body)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self._maps: list[TopoPlot] = []

    def set_series(
        self,
        times: list[float],
        values: list[list[float]],
        ch_names: list[str],
        positions: list[tuple[float, float]] | None = None,
        *,
        n_maps: int = 6,
        title: str = "",
    ) -> None:
        """*values* is n_times × n_channels (or n_ch × n_times if transposed)."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._maps.clear()
        if not times or not values or not ch_names:
            empty = QLabel("No ERP series", self)
            empty.setObjectName("mutedLabel")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(empty, 0, 0)
            return

        import numpy as np

        arr = np.asarray(values, dtype=float)
        # Accept (n_times, n_ch) or (n_ch, n_times)
        if arr.ndim != 2:
            return
        if arr.shape[1] == len(ch_names) and arr.shape[0] == len(times):
            series = arr  # time × ch
        elif arr.shape[0] == len(ch_names) and arr.shape[1] == len(times):
            series = arr.T
        else:
            # Best effort: assume time × ch if second dim matches
            series = arr if arr.shape[1] == len(ch_names) else arr.T

        pos = positions or positions_on_circle(len(ch_names))
        n = min(n_maps, len(times), series.shape[0])
        if n <= 0:
            return
        indices = [int(round(i * (len(times) - 1) / max(1, n - 1))) for i in range(n)]
        self._title.setText(title or f"ERP map series · {n} latencies")
        cols = min(3, n)
        for i, ti in enumerate(indices):
            topo = TopoPlot(self)
            topo.setMinimumSize(120, 120)
            row = list(series[ti])
            topo.set_map(row, ch_names, pos)
            ms = float(times[ti]) * 1000.0
            topo.set_title(f"{ms:.0f} ms")
            r, c = divmod(i, cols)
            self._grid.addWidget(topo, r, c)
            self._maps.append(topo)

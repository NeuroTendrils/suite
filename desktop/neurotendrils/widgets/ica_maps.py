"""EEGLAB pop_selectcomps-style ICA map browser."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme
from neurotendrils.widgets.topoplot import TopoPlot, positions_on_circle


class _Sparkline(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setMinimumWidth(160)
        self._samples: list[float] = []

    def set_samples(self, samples: list[float]) -> None:
        self._samples = [float(v) for v in samples]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())
        if len(self._samples) < 2:
            return
        lo, hi = min(self._samples), max(self._samples)
        if hi <= lo:
            hi = lo + 1.0
        path = QPainterPath()
        w = max(1, self.width() - 2)
        h = max(1, self.height() - 4)
        for i, v in enumerate(self._samples):
            x = 1 + (i / (len(self._samples) - 1)) * w
            y = 2 + (1.0 - (v - lo) / (hi - lo)) * h
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(theme.accent_color(), 1.4))
        painter.drawPath(path)


class _PsdMini(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setMinimumWidth(160)
        self._freqs: list[float] = []
        self._psd: list[float] = []

    def set_psd(self, freqs: list[float], psd: list[float]) -> None:
        self._freqs = [float(f) for f in freqs]
        self._psd = [float(v) for v in psd]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())
        if len(self._freqs) < 2 or len(self._psd) < 2:
            return
        lo, hi = min(self._psd), max(self._psd)
        if hi <= lo:
            hi = lo + 1.0
        f0, f1 = self._freqs[0], self._freqs[-1]
        fspan = f1 - f0 if f1 > f0 else 1.0
        plot = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        n = min(len(self._freqs), len(self._psd))
        for j in range(n):
            x = plot.left() + ((self._freqs[j] - f0) / fspan) * plot.width()
            y = plot.bottom() - ((self._psd[j] - lo) / (hi - lo)) * plot.height()
            if j == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.setPen(QPen(theme.muted_text_color(), 1.2))
        painter.drawPath(path)


class _IcHeader(QPushButton):
    """Clickable IC label — green when kept, red when excluded."""

    toggled_exclude = Signal(int, bool)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(f"IC{index:02d}", parent)
        self._index = index
        self._excluded = False
        self.setObjectName("planStepButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self._toggle)
        self._sync_style()

    @property
    def index(self) -> int:
        return self._index

    def is_excluded(self) -> bool:
        return self._excluded

    def set_excluded(self, excluded: bool) -> None:
        self._excluded = bool(excluded)
        self._sync_style()

    def _toggle(self) -> None:
        self._excluded = not self._excluded
        self._sync_style()
        self.toggled_exclude.emit(self._index, self._excluded)

    def _sync_style(self) -> None:
        if self._excluded:
            self.setStyleSheet(
                "QPushButton { background-color: #c8443c; color: white; border: none; "
                "border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 600; }"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background-color: #2a9d8f; color: white; border: none; "
                "border-radius: 4px; padding: 2px 6px; font-size: 11px; font-weight: 600; }"
            )


class _IcCell(QWidget):
    properties_requested = Signal(int)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index = index
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.header = _IcHeader(index, self)
        row.addWidget(self.header)
        props = QPushButton("Properties", self)
        props.setObjectName("ghostButton")
        props.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        props.clicked.connect(lambda: self.properties_requested.emit(self._index))
        row.addWidget(props)
        row.addStretch(1)
        layout.addLayout(row)
        self.topo = TopoPlot(self)
        self.topo.setMinimumSize(100, 100)
        layout.addWidget(self.topo, 1)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.properties_requested.emit(self._index)
        super().mouseDoubleClickEvent(event)


class IcaComponentProperties(QDialog):
    """Detail panel for one ICA component."""

    def __init__(
        self,
        index: int,
        *,
        map_values: list[float],
        ch_names: list[str],
        positions: list[tuple[float, float]] | None,
        waveform: list[float] | None,
        freqs: list[float] | None,
        psd: list[float] | None,
        excluded: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"IC{index:02d} properties")
        self._index = index
        self._excluded = excluded

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        title = QLabel(f"Component IC{index:02d}", self)
        title.setObjectName("inspectorTitle")
        root.addWidget(title)

        self._topo = TopoPlot(self)
        self._topo.setMinimumSize(180, 180)
        self._topo.set_map(map_values, ch_names, positions)
        root.addWidget(self._topo, 1)

        self._spark = _Sparkline(self)
        if waveform:
            self._spark.set_samples(waveform)
        root.addWidget(self._spark)

        self._psd = _PsdMini(self)
        if freqs and psd:
            self._psd.set_psd(freqs, psd)
        root.addWidget(self._psd)

        btn_row = QHBoxLayout()
        self._accept = QPushButton("ACCEPT (keep)", self)
        self._accept.setObjectName("secondaryButton")
        self._reject = QPushButton("REJECT (exclude)", self)
        self._reject.setObjectName("secondaryButton")
        btn_row.addWidget(self._accept)
        btn_row.addWidget(self._reject)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._accept.clicked.connect(lambda: self._set_excluded(False))
        self._reject.clicked.connect(lambda: self._set_excluded(True))
        self._sync_buttons()

    def _set_excluded(self, excluded: bool) -> None:
        self._excluded = excluded
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        keep_style = (
            "QPushButton { background-color: #2a9d8f; color: white; border: none; "
            "border-radius: 6px; padding: 6px 12px; font-weight: 600; }"
        )
        reject_style = (
            "QPushButton { background-color: #c8443c; color: white; border: none; "
            "border-radius: 6px; padding: 6px 12px; font-weight: 600; }"
        )
        if self._excluded:
            self._accept.setStyleSheet("")
            self._reject.setStyleSheet(reject_style)
        else:
            self._accept.setStyleSheet(keep_style)
            self._reject.setStyleSheet("")

    def is_excluded(self) -> bool:
        return self._excluded


class IcaMapBrowser(QWidget):
    """Grid of ICA scalp maps with exclude toggles (EEGLAB pop_selectcomps style)."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._hint = QLabel(
            "Click an IC header to toggle exclude (green = keep, red = reject). "
            "Double-click or Properties for detail.",
            self,
        )
        self._hint.setObjectName("mutedLabel")
        self._hint.setWordWrap(True)
        root.addWidget(self._hint)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        body = QWidget(scroll)
        self._grid = QGridLayout(body)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self._cells: list[_IcCell] = []
        self._summary: dict = {}
        self._positions: list[tuple[float, float]] = []
        self._ch_names: list[str] = []
        self._n = 0

    def set_summary(self, summary: dict) -> None:
        self._clear_grid()
        self._summary = dict(summary)
        self._ch_names = [str(n) for n in (summary.get("ch_names") or [])]
        raw_pos = summary.get("positions") or []
        if raw_pos and len(raw_pos) >= len(self._ch_names):
            self._positions = [(float(p[0]), float(p[1])) for p in raw_pos]
        else:
            self._positions = positions_on_circle(len(self._ch_names))

        maps = summary.get("maps") or []
        waveforms = summary.get("waveforms") or []
        spectra = summary.get("spectra") or []
        suggested = set(int(i) for i in (summary.get("suggested_exclude") or []))
        self._n = int(summary.get("n_components") or len(maps))

        cols = max(3, min(6, int(self._n ** 0.5) + 1))
        for i in range(self._n):
            cell = _IcCell(i, self)
            cell.header.set_excluded(i in suggested)
            cell.header.toggled_exclude.connect(self._on_toggle)
            cell.properties_requested.connect(self._open_properties)

            weights = list(maps[i]) if i < len(maps) else []
            if weights:
                cell.topo.set_map(weights, self._ch_names, self._positions)
            cell.topo.set_title(
                f"{float(summary.get('contributions', [0] * self._n)[i]) * 100:.1f}%"
                if i < len(summary.get("contributions") or [])
                else ""
            )

            row, col = divmod(i, cols)
            self._grid.addWidget(cell, row, col)
            self._cells.append(cell)

        self.changed.emit()

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cells.clear()

    def _on_toggle(self, _index: int, _excluded: bool) -> None:
        self.changed.emit()

    def _spectrum_for(self, index: int) -> tuple[list[float], list[float]]:
        spectra = self._summary.get("spectra") or []
        # Preferred: {"freqs": [...], "psd": [[comp0], [comp1], ...]}
        if isinstance(spectra, dict):
            freqs = [float(f) for f in (spectra.get("freqs") or [])]
            psds = spectra.get("psd") or []
            if index < len(psds):
                return freqs, [float(v) for v in psds[index]]
            return [], []
        freqs = self._summary.get("freqs")
        if not isinstance(spectra, list) or index >= len(spectra):
            return [], []
        entry = spectra[index]
        if isinstance(entry, dict):
            return [float(f) for f in (entry.get("freqs") or [])], [
                float(v) for v in (entry.get("psd") or [])
            ]
        if freqs is not None:
            return [float(f) for f in freqs], [float(v) for v in entry]
        return [], []

    def _open_properties(self, index: int) -> None:
        if index < 0 or index >= len(self._cells):
            return
        maps = self._summary.get("maps") or []
        waveforms = self._summary.get("waveforms") or []
        freqs, psd = self._spectrum_for(index)
        dlg = IcaComponentProperties(
            index,
            map_values=list(maps[index]) if index < len(maps) else [],
            ch_names=self._ch_names,
            positions=self._positions,
            waveform=list(waveforms[index]) if index < len(waveforms) else None,
            freqs=freqs or None,
            psd=psd or None,
            excluded=self._cells[index].header.is_excluded(),
            parent=self,
        )
        dlg.exec()
        self._cells[index].header.set_excluded(dlg.is_excluded())
        self.changed.emit()

    def exclude_indices(self) -> list[int]:
        return [c.header.index for c in self._cells if c.header.is_excluded()]

    def exclude_csv(self) -> str:
        return ",".join(str(i) for i in self.exclude_indices())

"""Scrollable multichannel EEG viewer with event markers and bad-span paint.

Manual prep widget — not a NeuroFlow recipe step.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.theme import Theme


@dataclass
class ViewerEvent:
    onset: float  # seconds
    duration: float
    label: str
    kind: str = "event"  # event | bad


class EegTraceCanvas(QWidget):
    """Paint a time window of multichannel traces + markers."""

    badSpanPainted = Signal(float, float)  # tmin, tmax seconds

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("eegTraceCanvas")
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self._data: np.ndarray | None = None  # (n_ch, n_times), preferably demeaned
        self._sfreq = 250.0
        self._ch_names: list[str] = []
        self._events: list[ViewerEvent] = []
        self._t0 = 0.0
        self._window_sec = 10.0
        self._amp_scale = 1.0
        self._paint_bad = False
        self._drag_start: float | None = None
        self._drag_end: float | None = None
        self._global_scale = 1.0

    def set_recording(
        self,
        data: np.ndarray,
        *,
        sfreq: float,
        ch_names: list[str],
        events: list[ViewerEvent] | None = None,
    ) -> None:
        if data.ndim != 2:
            raise ValueError("data must be (n_channels, n_times)")
        arr = np.asarray(data, dtype=np.float64)
        # Demean so DC bias (common in raw µV exports) does not flatten traces.
        arr = arr - np.mean(arr, axis=1, keepdims=True)
        self._data = arr
        self._sfreq = float(sfreq) if sfreq > 0 else 250.0
        self._ch_names = list(ch_names) if ch_names else [
            f"ch{i}" for i in range(self._data.shape[0])
        ]
        self._events = list(events or [])
        self._t0 = 0.0
        # Global robust scale from full preview (MAD-like).
        mad = np.median(np.abs(self._data), axis=1)
        mad = mad[mad > 0]
        self._global_scale = float(np.median(mad)) if mad.size else 1.0
        if self._global_scale < 1e-20:
            self._global_scale = 1.0
        self.update()

    def clear(self) -> None:
        self._data = None
        self._events = []
        self.update()

    def duration_sec(self) -> float:
        if self._data is None or self._sfreq <= 0:
            return 0.0
        return float(self._data.shape[1] / self._sfreq)

    def set_window(self, t0: float, window_sec: float) -> None:
        self._t0 = max(0.0, float(t0))
        self._window_sec = max(0.5, float(window_sec))
        self.update()

    def set_amp_scale(self, scale: float) -> None:
        self._amp_scale = max(0.05, float(scale))
        self.update()

    def set_paint_bad(self, enabled: bool) -> None:
        self._paint_bad = bool(enabled)
        self.setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )

    def add_event(self, event: ViewerEvent) -> None:
        self._events.append(event)
        self.update()

    def events(self) -> list[ViewerEvent]:
        return list(self._events)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        step = self._window_sec * 0.2 * (-1 if delta > 0 else 1)
        self._t0 = max(
            0.0, min(self._t0 + step, max(0.0, self.duration_sec() - self._window_sec))
        )
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if not self._paint_bad or self._data is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = self._x_to_time(event.position().x())
            self._drag_end = self._drag_start
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._drag_start is None:
            return
        self._drag_end = self._x_to_time(event.position().x())
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._drag_start is None or self._drag_end is None:
            return
        tmin, tmax = sorted((self._drag_start, self._drag_end))
        self._drag_start = None
        self._drag_end = None
        if tmax - tmin >= 0.05:
            self._events.append(ViewerEvent(tmin, tmax - tmin, "BAD", kind="bad"))
            self.badSpanPainted.emit(tmin, tmax)
        self.update()

    def _x_to_time(self, x: float) -> float:
        margin_l, margin_r = 56.0, 12.0
        width = max(1.0, self.width() - margin_l - margin_r)
        frac = (x - margin_l) / width
        frac = max(0.0, min(1.0, frac))
        return self._t0 + frac * self._window_sec

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        theme = Theme.instance()
        painter.fillRect(self.rect(), theme.surface_color())

        if self._data is None or self._data.size == 0:
            painter.setPen(theme.muted_text_color())
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No recording loaded"
            )
            return

        margin_l, margin_r, margin_t, margin_b = 56.0, 12.0, 16.0, 28.0
        plot = self.rect().adjusted(
            int(margin_l), int(margin_t), -int(margin_r), -int(margin_b)
        )
        n_ch, n_times = self._data.shape
        sfreq = self._sfreq
        i0 = int(self._t0 * sfreq)
        i1 = min(n_times, int((self._t0 + self._window_sec) * sfreq))
        if i1 - i0 < 2:
            painter.setPen(theme.muted_text_color())
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "Scroll to data / widen window"
            )
            return

        segment = self._data[:, i0:i1]
        # Per-channel robust scale on demeaned window (ignore DC).
        scales = np.median(np.abs(segment), axis=1)
        scales = np.where(scales < 1e-12, self._global_scale, scales)
        scales = np.where(scales < 1e-12, 1.0, scales)
        row_h = plot.height() / max(1, min(n_ch, 32))

        for ev in self._events:
            if ev.onset + ev.duration < self._t0 or ev.onset > self._t0 + self._window_sec:
                continue
            x0 = plot.left() + ((ev.onset - self._t0) / self._window_sec) * plot.width()
            x1 = plot.left() + (
                (ev.onset + max(ev.duration, 0.01) - self._t0) / self._window_sec
            ) * plot.width()
            color = (
                QColor(220, 80, 80, 60)
                if ev.kind == "bad"
                else QColor(
                    theme.accent_color().red(),
                    theme.accent_color().green(),
                    theme.accent_color().blue(),
                    50,
                )
            )
            painter.fillRect(
                int(x0), plot.top(), max(2, int(x1 - x0)), plot.height(), color
            )
            painter.setPen(theme.muted_text_color())
            painter.drawText(int(x0) + 2, plot.top() + 12, ev.label[:24])

        if self._drag_start is not None and self._drag_end is not None:
            a, b = sorted((self._drag_start, self._drag_end))
            x0 = plot.left() + ((a - self._t0) / self._window_sec) * plot.width()
            x1 = plot.left() + ((b - self._t0) / self._window_sec) * plot.width()
            painter.fillRect(
                int(x0),
                plot.top(),
                max(2, int(x1 - x0)),
                plot.height(),
                QColor(220, 80, 80, 80),
            )

        pen = QPen(theme.text_color())
        pen.setWidthF(1.2)
        painter.setPen(pen)
        max_ch = min(n_ch, 32)
        # Decimate for paint if dense (>800 pts) so Qt path stays sharp.
        n_seg = segment.shape[1]
        paint_step = max(1, n_seg // 800)
        for ci in range(max_ch):
            y_mid = plot.top() + (ci + 0.5) * row_h
            samples = segment[ci, ::paint_step]
            trace = samples / scales[ci] * (row_h * 0.40) * self._amp_scale
            n = int(trace.shape[0])
            if n < 2:
                continue
            path = QPainterPath()
            path_x0 = float(plot.left())
            width = float(plot.width())
            for ti in range(n):
                x = path_x0 + (ti / max(1, n - 1)) * width
                y = y_mid - float(trace[ti])
                if ti == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)
            painter.setPen(theme.muted_text_color())
            painter.drawText(
                4,
                int(y_mid + 4),
                self._ch_names[ci][:10] if ci < len(self._ch_names) else f"ch{ci}",
            )
            painter.setPen(pen)

        painter.setPen(theme.muted_text_color())
        painter.drawText(plot.left(), self.height() - 8, f"{self._t0:.1f}s")
        painter.drawText(
            plot.right() - 48,
            self.height() - 8,
            f"{self._t0 + self._window_sec:.1f}s",
        )


class EegViewer(QWidget):
    """Toolbar + scrollable canvas for manual EEG inspection."""

    badSpanPainted = Signal(float, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("eegViewer")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self._status = QLabel("No recording", self)
        self._status.setObjectName("mutedLabel")
        tools.addWidget(self._status, 1)

        self._paint_btn = QPushButton("Paint bad", self)
        self._paint_btn.setCheckable(True)
        self._paint_btn.setObjectName("ghostButton")
        self._paint_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paint_btn.toggled.connect(self._on_paint_toggled)
        tools.addWidget(self._paint_btn)

        tools.addWidget(QLabel("Amp", self))
        self._amp = QSlider(Qt.Orientation.Horizontal, self)
        self._amp.setRange(1, 80)
        self._amp.setValue(20)  # default 2.0× so AC is visible
        self._amp.setFixedWidth(100)
        self._amp.valueChanged.connect(lambda v: self._canvas.set_amp_scale(v / 10.0))
        tools.addWidget(self._amp)

        tools.addWidget(QLabel("Window", self))
        self._win = QSlider(Qt.Orientation.Horizontal, self)
        self._win.setRange(2, 60)
        self._win.setValue(10)
        self._win.setFixedWidth(100)
        self._win.valueChanged.connect(self._on_window_changed)
        tools.addWidget(self._win)
        root.addLayout(tools)

        self._canvas = EegTraceCanvas(self)
        self._canvas.badSpanPainted.connect(self.badSpanPainted.emit)
        self._canvas.set_amp_scale(self._amp.value() / 10.0)
        root.addWidget(self._canvas, 1)

        scrub = QHBoxLayout()
        scrub.addWidget(QLabel("Scroll", self))
        self._scrub = QSlider(Qt.Orientation.Horizontal, self)
        self._scrub.setRange(0, 1000)
        self._scrub.valueChanged.connect(self._on_scrub)
        scrub.addWidget(self._scrub, 1)
        root.addLayout(scrub)

    def load_path(self, path: str) -> str | None:
        """Load a recording from disk. Returns error message or None."""
        try:
            from neurotendrils.core.ingestion.readers import read_recording
        except Exception as exc:  # noqa: BLE001
            return str(exc)
        try:
            raw = read_recording(path, preload=True)
        except Exception as exc:  # noqa: BLE001
            return str(exc)

        import mne

        if isinstance(raw, mne.Epochs):
            data = raw.get_data()
            if data.size == 0:
                return "Recording has no samples."
            flat = data.transpose(1, 0, 2).reshape(data.shape[1], -1)
            sfreq = float(raw.info["sfreq"])
            ch_names = list(raw.ch_names)
            events: list[ViewerEvent] = []
        else:
            picks = mne.pick_types(raw.info, eeg=True, eog=True, meg=False, exclude=[])
            if len(picks) == 0:
                picks = np.arange(min(16, len(raw.ch_names)))
            else:
                picks = picks[:16]
            sfreq = float(raw.info["sfreq"])
            max_samples = int(sfreq * 30)
            data = raw.get_data(
                picks=picks, start=0, stop=min(max_samples, raw.n_times)
            )
            decim = max(1, int(round(sfreq / 100.0)))
            data = data[:, ::decim]
            sfreq = sfreq / decim
            ch_names = [raw.ch_names[i] for i in picks]
            events = []
            ann = getattr(raw, "annotations", None)
            if ann is not None:
                for onset, duration, desc in zip(
                    ann.onset, ann.duration, ann.description
                ):
                    if float(onset) > 30.0:
                        break
                    kind = "bad" if str(desc).upper().startswith("BAD") else "event"
                    events.append(
                        ViewerEvent(
                            float(onset), float(duration), str(desc), kind=kind
                        )
                    )

        self.set_array(data, sfreq=sfreq, ch_names=ch_names, events=events)
        return None

    def set_array(
        self,
        data: np.ndarray,
        *,
        sfreq: float,
        ch_names: list[str] | None = None,
        events: list[ViewerEvent] | None = None,
    ) -> None:
        arr = np.asarray(data, dtype=np.float64)
        self._canvas.set_recording(
            arr,
            sfreq=sfreq,
            ch_names=ch_names or [],
            events=events,
        )
        pp = float(np.percentile(np.abs(arr - arr.mean(axis=1, keepdims=True)), 95))
        self._status.setText(
            f"{arr.shape[0]} ch · {sfreq:.0f} Hz · {self._canvas.duration_sec():.1f}s"
            f" · ~{pp:.3g} peak (demeaned)"
        )
        self._scrub.blockSignals(True)
        self._scrub.setValue(0)
        self._scrub.blockSignals(False)
        self._on_window_changed(self._win.value())

    def events(self) -> list[ViewerEvent]:
        return self._canvas.events()

    def _on_paint_toggled(self, on: bool) -> None:
        self._canvas.set_paint_bad(on)

    def _on_window_changed(self, value: int) -> None:
        self._canvas.set_window(self._canvas._t0, float(value))
        self._sync_scrub_range()

    def _on_scrub(self, value: int) -> None:
        dur = self._canvas.duration_sec()
        win = float(self._win.value())
        max_t0 = max(0.0, dur - win)
        t0 = (value / 1000.0) * max_t0 if max_t0 > 0 else 0.0
        self._canvas.set_window(t0, win)

    def _sync_scrub_range(self) -> None:
        pass

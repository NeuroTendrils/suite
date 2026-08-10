"""Heuristic artifact suggestions. Never mutates raw; UI must confirm."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import numpy as np

from suite_backend.domain.models import DataStream, RecommendationResult, Recording
from suite_backend.scientific.io.canonical import load_primary_eeg_raw, load_stream_samples


def _rid() -> str:
    return f"sug_{uuid4().hex[:12]}"


def detect_artifacts(
    recording: Recording,
    streams: list[DataStream] | None = None,
    **_: Any,
) -> RecommendationResult:
    """
    Placeholder detectors (amplitude / flatline / high-PTP windows).

    Returns suggestions only — never auto-applies or deletes data.
    """
    streams = streams or []
    recommendations: list[dict[str, Any]] = []
    warnings = [
        "heuristic placeholder detectors — not a validated clinical/research QC pipeline",
        "confirm every suggestion before applying; raw samples are never mutated",
    ]

    try:
        samples = None
        eeg = next((s for s in streams if s.modality.value == "eeg"), None)
        if eeg is not None:
            samples = load_stream_samples(eeg)
            data = samples.data
            times = samples.times
            names = samples.channel_names
            sfreq = samples.sfreq
        else:
            raw = load_primary_eeg_raw(recording, streams)
            data = raw.get_data()
            times = raw.times
            names = list(raw.ch_names)
            sfreq = float(raw.info["sfreq"])
    except Exception as exc:  # noqa: BLE001
        return RecommendationResult(
            recommendations=[],
            warnings=warnings + [f"could not load EEG for detection: {exc}"],
            confidence=None,
            explanation="artifact detection requires readable EEG samples",
        )

    if data.size == 0:
        return RecommendationResult(
            recommendations=[],
            warnings=warnings + ["empty EEG data"],
            confidence=0.0,
            explanation=None,
        )

    # Per-channel std (exclude stim-like names)
    stds = np.std(data, axis=1)
    med = float(np.median(stds[stds > 0])) if np.any(stds > 0) else 1.0
    amp_thr = med * 8.0
    flat_thr = med * 0.02 if med > 0 else 1e-12

    for i, name in enumerate(names):
        n = (name or "").lower()
        if n.startswith("sti") or n in {"stim", "trigger", "marker"}:
            continue
        s = float(stds[i])
        if s < flat_thr:
            recommendations.append(
                {
                    "id": _rid(),
                    "kind": "bad_channel",
                    "channel": name,
                    "method": "flatline_std",
                    "threshold": flat_thr,
                    "value": s,
                    "reason": f"near-flat channel (std={s:.3g})",
                    "confidence": 0.35,
                    "placeholder": True,
                }
            )
        elif s > amp_thr:
            recommendations.append(
                {
                    "id": _rid(),
                    "kind": "bad_channel",
                    "channel": name,
                    "method": "amplitude_std",
                    "threshold": amp_thr,
                    "value": s,
                    "reason": f"high amplitude variance (std={s:.3g})",
                    "confidence": 0.4,
                    "placeholder": True,
                }
            )

    # Sliding-window peak-to-peak on global mean abs
    win = max(1, int(sfreq * 0.5))
    step = max(1, win // 2)
    g = np.mean(np.abs(data), axis=0)
    if g.size >= win:
        ptp_vals = []
        for start in range(0, g.size - win + 1, step):
            seg = g[start : start + win]
            ptp_vals.append((start, float(np.ptp(seg))))
        if ptp_vals:
            ptps = np.array([p for _, p in ptp_vals], dtype=np.float64)
            thr = float(np.median(ptps) * 6.0 + 1e-12)
            for start, ptp in ptp_vals:
                if ptp < thr:
                    continue
                t0 = float(times[start]) if start < len(times) else start / sfreq
                t1 = float(times[min(start + win - 1, len(times) - 1)])
                recommendations.append(
                    {
                        "id": _rid(),
                        "kind": "bad_segment",
                        "start": t0,
                        "end": t1,
                        "method": "ptp_window",
                        "threshold": thr,
                        "value": ptp,
                        "reason": f"high peak-to-peak window (ptp={ptp:.3g})",
                        "confidence": 0.3,
                        "placeholder": True,
                    }
                )
                if sum(1 for r in recommendations if r["kind"] == "bad_segment") >= 8:
                    break

    return RecommendationResult(
        recommendations=recommendations,
        warnings=warnings,
        confidence=0.35 if recommendations else 0.2,
        explanation=(
            "Placeholder QC: std outliers → bad_channel; high PTP windows → bad_segment. "
            "Apply via artifacts.apply (annotations/decisions only)."
        ),
    )

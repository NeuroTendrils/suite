"""Continuous cleaning without EEGLAB ASR — amplitude / flat spans → new artifact."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from suite_backend.domain.models import DataStream, DatasetArtifact, Recording
from suite_backend.neuroflow.signal import load_raw_for_recording


def _bad_spans_amplitude(
    data: np.ndarray,
    sfreq: float,
    *,
    win_sec: float = 0.5,
    z_thresh: float = 5.0,
) -> list[tuple[float, float]]:
    """Flag windows where global |signal| z-score exceeds threshold."""
    g = np.mean(np.abs(data), axis=0)
    win = max(1, int(sfreq * win_sec))
    step = max(1, win // 2)
    spans: list[tuple[float, float]] = []
    if g.size < win:
        return spans
    vals = []
    starts = []
    for i0 in range(0, g.size - win + 1, step):
        starts.append(i0)
        vals.append(float(np.mean(g[i0 : i0 + win])))
    arr = np.asarray(vals, dtype=np.float64)
    mu, sd = float(np.mean(arr)), float(np.std(arr) + 1e-12)
    for i0, v in zip(starts, arr, strict=True):
        if (v - mu) / sd >= z_thresh:
            t0 = i0 / sfreq
            t1 = (i0 + win) / sfreq
            if spans and t0 <= spans[-1][1] + 1e-6:
                spans[-1] = (spans[-1][0], max(spans[-1][1], t1))
            else:
                spans.append((t0, t1))
    return spans


def clean_continuous(
    recording: Recording,
    *,
    study_id: str,
    artifact_dir: Path,
    streams: list[DataStream] | None = None,
    z_thresh: float = 5.0,
    also_drop_annotated: bool = True,
) -> dict[str, Any]:
    """
    Drop high-amplitude windows (and existing BAD/artifact annotations) into a new FIF.

    Not ASR/CleanRawdata — honest amplitude-based continuous clean for EEGLAB-parity path.
    """
    import mne

    raw = load_raw_for_recording(recording, streams).copy().load_data()
    sfreq = float(raw.info["sfreq"])
    data = raw.get_data()
    spans = _bad_spans_amplitude(data, sfreq, z_thresh=z_thresh)

    if also_drop_annotated:
        for a in raw.annotations:
            desc = str(a["description"]).lower()
            if "bad" in desc or "artifact" in desc:
                spans.append((float(a["onset"]), float(a["onset"] + a["duration"])))

    # merge overlaps
    spans = sorted(spans)
    merged: list[tuple[float, float]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))

    duration = float(raw.times[-1]) if len(raw.times) else 0.0
    # good intervals = complement of merged bad spans
    goods: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in merged:
        a = max(0.0, min(duration, a))
        b = max(0.0, min(duration, b))
        if a > cursor + 1.0 / sfreq:
            goods.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < duration - 1.0 / sfreq:
        goods.append((cursor, duration))

    if not goods:
        raise ValueError("continuous clean would remove all data — lower z_thresh")

    pieces = []
    for t0, t1 in goods:
        if t1 - t0 < 2.0 / sfreq:
            continue
        pieces.append(raw.copy().crop(tmin=t0, tmax=t1, include_tmax=False))
    if not pieces:
        raise ValueError("no remaining good segments after clean")
    cleaned = pieces[0]
    if len(pieces) > 1:
        cleaned = mne.concatenate_raws(pieces, preload=True)

    artifact_dir.mkdir(parents=True, exist_ok=True)
    out = artifact_dir / f"clean_{recording.id}_raw.fif"
    cleaned.save(out, overwrite=True, verbose=False)
    checksum = hashlib.sha256(out.read_bytes()).hexdigest()
    artifact = DatasetArtifact(
        type="cleaned_recording",
        parent_id=recording.artifact_id,
        source=recording.id,
        operation="clean_continuous_amplitude",
        parameters={
            "z_thresh": z_thresh,
            "n_bad_spans": len(merged),
            "n_good_segments": len(pieces),
            "note": "not ASR — amplitude z-score window drop",
        },
        checksum=checksum,
        paths={"fif": str(out)},
        recording_id=recording.id,
        study_id=study_id,
    )
    return {
        "artifact": artifact,
        "n_bad_spans": len(merged),
        "bad_spans": [{"start": a, "end": b} for a, b in merged],
        "duration_before": duration,
        "duration_after": float(cleaned.times[-1]) if len(cleaned.times) else 0.0,
        "warning": "amplitude-based clean, not EEGLAB CleanRawdata/ASR",
    }

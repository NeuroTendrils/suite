"""Apply catalog preprocessing steps to MNE Raw / Epochs.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .repro import ICA_RANDOM_STATE
from .steps import validate_params


class ApplyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def apply_step(data: Any, step_id: str, params: dict[str, Any]) -> Any:
    """Apply one catalog step. *data* is mne.io.BaseRaw or mne.Epochs."""
    error = validate_params(step_id, params)
    if error:
        raise ApplyError("invalid_params", error)

    handlers = {
        "filter": _apply_filter,
        "notch": _apply_notch,
        "reref": _apply_reref,
        "resample": _apply_resample,
        "ica": _apply_ica,
        "epoch": _apply_epoch,
        "event_epoch": _apply_event_epoch,
        "augment": _apply_augment,
    }
    handler = handlers.get(step_id)
    if handler is None:
        raise ApplyError("unknown_step", f"unknown step: {step_id}")
    return handler(data, params)


def _require_raw(data: Any, step_id: str) -> Any:
    import mne

    if isinstance(data, mne.Epochs):
        raise ApplyError(
            "invalid_order",
            f"step “{step_id}” requires continuous Raw data; epoch earlier in the plan.",
        )
    return data


def _require_epochs(data: Any, step_id: str) -> Any:
    import mne

    if not isinstance(data, mne.Epochs):
        raise ApplyError(
            "invalid_order",
            f"step “{step_id}” requires Epochs; run event_epoch (or epoch) first.",
        )
    return data


def _ensure_preloaded(raw: Any) -> Any:
    if not raw.preload:
        raw.load_data()
    return raw


def _apply_filter(data: Any, params: dict[str, Any]) -> Any:
    raw = _ensure_preloaded(_require_raw(data, "filter"))
    l_freq = float(params.get("l_freq", 0.0))
    h_freq = float(params.get("h_freq", 0.0))
    method = str(params.get("method", "fir"))
    raw.filter(
        l_freq=None if l_freq <= 0 else l_freq,
        h_freq=None if h_freq <= 0 else h_freq,
        method=method,
        verbose="ERROR",
    )
    return raw


def _apply_notch(data: Any, params: dict[str, Any]) -> Any:
    raw = _ensure_preloaded(_require_raw(data, "notch"))
    base = float(params.get("freq", "60"))
    freqs: list[float] = [base]
    if bool(params.get("harmonics", True)):
        freqs.extend([base * 2.0, base * 3.0])
    nyquist = float(raw.info["sfreq"]) / 2.0
    freqs = [f for f in freqs if f < nyquist]
    if not freqs:
        return raw
    raw.notch_filter(freqs=freqs, verbose="ERROR")
    return raw


def _apply_reref(data: Any, params: dict[str, Any]) -> Any:
    raw = _ensure_preloaded(_require_raw(data, "reref"))
    reference = str(params.get("reference", "average"))
    if reference == "average":
        raw.set_eeg_reference(ref_channels="average", projection=False, verbose="ERROR")
    else:
        channel = str(params.get("channel", "")).strip()
        if channel not in raw.ch_names:
            raise ApplyError(
                "invalid_params",
                f"reref: channel “{channel}” not found in recording.",
            )
        raw.set_eeg_reference(ref_channels=[channel], projection=False, verbose="ERROR")
    return raw


def _apply_resample(data: Any, params: dict[str, Any]) -> Any:
    raw = _ensure_preloaded(_require_raw(data, "resample"))
    sfreq = float(params["sfreq"])
    raw.resample(sfreq, verbose="ERROR")
    return raw


def _parse_exclude(text: str) -> list[int]:
    if not text.strip():
        return []
    out: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError as exc:
            raise ApplyError(
                "invalid_params",
                f"ica: exclude must be comma-separated integers, got “{part}”.",
            ) from exc
    return out


def _apply_ica(data: Any, params: dict[str, Any]) -> Any:
    from mne.preprocessing import ICA

    raw = _ensure_preloaded(_require_raw(data, "ica"))
    n_components = params.get("n_components", 0.99)
    if isinstance(n_components, float) and n_components > 1.0:
        n_components = int(round(n_components))

    ica = ICA(
        n_components=n_components,
        random_state=ICA_RANDOM_STATE,
        max_iter="auto",
        verbose="ERROR",
    )
    try:
        sfreq = float(raw.info["sfreq"])
        decim = max(1, int(round(sfreq / 100.0)))
        fit_raw = raw
        if len(raw.times) and float(raw.times[-1]) > 60.0:
            fit_raw = raw.copy().crop(tmin=0.0, tmax=60.0, include_tmax=True)
        ica.fit(fit_raw, decim=decim, verbose="ERROR")
    except Exception as exc:  # noqa: BLE001
        raise ApplyError("step_failed", f"ica fit failed: {exc}") from exc

    exclude = set(_parse_exclude(str(params.get("exclude", ""))))
    if bool(params.get("find_bads_eog", True)):
        eog_indices: list[int] = []
        try:
            eog_indices, _ = ica.find_bads_eog(raw, verbose="ERROR")
        except Exception:
            eog_indices = []
        exclude.update(int(i) for i in eog_indices)

    ica.exclude = sorted(exclude)
    try:
        return ica.apply(raw, verbose="ERROR")
    except Exception as exc:  # noqa: BLE001
        raise ApplyError("step_failed", f"ica apply failed: {exc}") from exc


def _apply_epoch(data: Any, params: dict[str, Any]) -> Any:
    import mne

    raw = _ensure_preloaded(_require_raw(data, "epoch"))
    duration = float(params["duration"])
    overlap = float(params.get("overlap", 0.0))
    try:
        epochs = mne.make_fixed_length_epochs(
            raw,
            duration=duration,
            overlap=overlap,
            preload=True,
            verbose="ERROR",
        )
    except Exception as exc:  # noqa: BLE001
        raise ApplyError("step_failed", f"epoch failed: {exc}") from exc
    return epochs


def _parse_event_labels(text: str) -> list[str] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    labels = [part.strip() for part in raw.split(",") if part.strip()]
    return labels or None


def _apply_event_epoch(data: Any, params: dict[str, Any]) -> Any:
    import mne

    raw = _ensure_preloaded(_require_raw(data, "event_epoch"))
    tmin = float(params.get("tmin", -0.2))
    tmax = float(params.get("tmax", 0.8))
    b_tmin = float(params.get("baseline_tmin", tmin))
    b_tmax = float(params.get("baseline_tmax", 0.0))
    baseline = None if abs(b_tmin - b_tmax) < 1e-12 else (b_tmin, b_tmax)
    wanted = _parse_event_labels(str(params.get("event_ids", "")))

    try:
        events, event_id = mne.events_from_annotations(raw, verbose="ERROR")
    except Exception as exc:  # noqa: BLE001
        raise ApplyError(
            "step_failed",
            f"event_epoch: could not read annotations as events: {exc}",
        ) from exc

    if events is None or len(events) == 0:
        # Fall back to stim-channel events when present.
        try:
            events = mne.find_events(raw, shortest_event=1, verbose="ERROR")
            event_id = {str(code): int(code) for code in sorted(set(events[:, 2]))}
        except Exception as exc:  # noqa: BLE001
            raise ApplyError(
                "step_failed",
                "event_epoch: no annotations or stim events on recording.",
            ) from exc

    if not event_id:
        raise ApplyError("step_failed", "event_epoch: no event ids found.")

    # Drop BAD* / edge annotations from the id map.
    filtered_id = {
        name: code
        for name, code in event_id.items()
        if not str(name).upper().startswith("BAD")
        and str(name).upper() not in {"EDGE", "BAD BOUNDARY"}
    }
    if wanted is not None:
        wanted_set = {w.lower() for w in wanted}
        filtered_id = {
            name: code
            for name, code in filtered_id.items()
            if str(name).lower() in wanted_set
        }
    if not filtered_id:
        raise ApplyError(
            "step_failed",
            "event_epoch: no matching non-bad events to epoch.",
        )

    keep_codes = set(filtered_id.values())
    events = events[np.isin(events[:, 2], list(keep_codes))]
    if len(events) == 0:
        raise ApplyError("step_failed", "event_epoch: events list empty after filter.")

    reject_by_annotation = True
    try:
        epochs = mne.Epochs(
            raw,
            events,
            event_id=filtered_id,
            tmin=tmin,
            tmax=tmax,
            baseline=baseline,
            preload=True,
            reject_by_annotation=reject_by_annotation,
            verbose="ERROR",
        )
    except Exception as exc:  # noqa: BLE001
        raise ApplyError("step_failed", f"event_epoch failed: {exc}") from exc

    if len(epochs) == 0:
        raise ApplyError("step_failed", "event_epoch: produced zero epochs.")
    return epochs


def _apply_augment(data: Any, params: dict[str, Any]) -> Any:
    """Propose synthetic epochs to reach per_class_min; tag metadata."""
    import mne
    import pandas as pd

    epochs = _require_epochs(data, "augment")
    if not epochs.preload:
        epochs.load_data()

    method = str(params.get("method", "noise"))
    per_class_min = int(params.get("per_class_min", 8))
    noise_std = float(params.get("noise_std", 0.05))
    time_shift_frac = float(params.get("time_shift_frac", 0.05))
    dropout_frac = float(params.get("dropout_frac", 0.1))
    seed = int(params.get("seed", 42))
    rng = np.random.default_rng(seed)

    # Build class labels from event_id inverse.
    id_to_name = {int(v): str(k) for k, v in (epochs.event_id or {}).items()}
    event_codes = [int(c) for c in epochs.events[:, 2]]
    labels = [id_to_name.get(code, str(code)) for code in event_codes]

    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1

    X = epochs.get_data(copy=True)  # (n_epochs, n_channels, n_times)
    meta_rows: list[dict[str, Any]] = []
    if epochs.metadata is not None:
        meta_rows = epochs.metadata.to_dict(orient="records")
    else:
        meta_rows = [{"augmented": False, "class": labels[i]} for i in range(len(labels))]

    new_trials: list[np.ndarray] = []
    new_events: list[list[int]] = []
    new_meta: list[dict[str, Any]] = []
    next_sample = int(epochs.events[-1, 0]) + int(epochs.times.size) if len(epochs) else 0

    for label, count in list(counts.items()):
        need = max(0, per_class_min - count)
        if need == 0:
            continue
        source_idx = [i for i, name in enumerate(labels) if name == label]
        if not source_idx:
            continue
        code = int(epochs.event_id[label]) if label in epochs.event_id else event_codes[source_idx[0]]
        for _ in range(need):
            src = int(rng.choice(source_idx))
            trial = np.array(X[src], copy=True)
            if method == "noise":
                ch_std = np.std(trial, axis=1, keepdims=True)
                ch_std = np.where(ch_std < 1e-12, 1.0, ch_std)
                trial = trial + rng.normal(0.0, noise_std, size=trial.shape) * ch_std
            elif method == "time_shift":
                n_times = trial.shape[1]
                max_shift = max(1, int(round(time_shift_frac * n_times)))
                shift = int(rng.integers(-max_shift, max_shift + 1))
                trial = np.roll(trial, shift, axis=1)
            elif method == "channel_dropout":
                n_ch = trial.shape[0]
                n_drop = max(1, int(round(dropout_frac * n_ch)))
                drop = rng.choice(n_ch, size=min(n_drop, n_ch), replace=False)
                trial[drop, :] = 0.0
            else:
                raise ApplyError("invalid_params", f"augment: unknown method {method}")

            new_trials.append(trial)
            next_sample += int(epochs.times.size)
            new_events.append([next_sample, 0, code])
            new_meta.append(
                {
                    "augmented": True,
                    "class": label,
                    "source_index": src,
                    "augment_method": method,
                }
            )

    if not new_trials:
        # Nothing to add — ensure metadata column exists.
        if epochs.metadata is None:
            epochs.metadata = pd.DataFrame(meta_rows)
        elif "augmented" not in epochs.metadata.columns:
            epochs.metadata = epochs.metadata.copy()
            epochs.metadata["augmented"] = False
        return epochs

    all_data = np.concatenate([X, np.stack(new_trials, axis=0)], axis=0)
    all_events = np.concatenate(
        [epochs.events, np.asarray(new_events, dtype=epochs.events.dtype)],
        axis=0,
    )
    all_meta = pd.DataFrame(meta_rows + new_meta)

    info = epochs.info.copy()
    out = mne.EpochsArray(
        all_data,
        info,
        events=all_events,
        tmin=float(epochs.tmin),
        event_id=dict(epochs.event_id),
        metadata=all_meta,
        verbose="ERROR",
    )
    return out

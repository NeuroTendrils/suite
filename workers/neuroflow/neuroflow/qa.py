"""QA helpers: ICA component summary, ERP averages, spectra, ERP image, augment.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def _load_saved_ica_summary(raw_path: str) -> dict[str, Any] | None:
    """Prefer artifacts written during the NeuroFlow run (no ICA refit)."""
    p = Path(raw_path)
    candidates = [
        p.parent / "ica_summary.json",
        p.with_name("ica_summary.json"),
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("contributions") is not None:
            return data
    return None


def ica_component_summary(raw_path: str, *, n_components: float | int = 0.99) -> dict[str, Any]:
    """Return ICA contributions + maps; load run artifacts when present (fast path)."""
    saved = _load_saved_ica_summary(raw_path)
    if saved is not None:
        return saved

    # Slow path: fit ICA (prefer running a NeuroFlow plan so artifacts are cached).
    from .apply import _channel_xy, _component_spectra
    from .repro import ICA_RANDOM_STATE

    import mne
    from mne.preprocessing import ICA

    raw = mne.io.read_raw(raw_path, preload=True, verbose="ERROR")
    ica = ICA(
        n_components=n_components,
        random_state=ICA_RANDOM_STATE,
        max_iter="auto",
        verbose="ERROR",
    )
    sfreq = float(raw.info["sfreq"])
    decim = max(1, int(round(sfreq / 100.0)))
    fit_raw = raw
    if len(raw.times) and float(raw.times[-1]) > 60.0:
        fit_raw = raw.copy().crop(tmin=0.0, tmax=60.0, include_tmax=True)
    ica.fit(fit_raw, decim=decim, verbose="ERROR")

    sources = ica.get_sources(fit_raw).get_data()
    contrib = np.mean(np.abs(sources), axis=1)
    total = float(np.sum(contrib)) or 1.0
    fractions = (contrib / total).tolist()

    eog_indices: list[int] = []
    try:
        eog_indices, _ = ica.find_bads_eog(raw, verbose="ERROR")
    except Exception:  # noqa: BLE001
        eog_indices = []

    try:
        mixing = ica.get_components()
        maps = [[float(v) for v in mixing[:, i]] for i in range(mixing.shape[1])]
    except Exception:  # noqa: BLE001
        maps = []

    n_keep = min(sources.shape[1], int(sfreq * 2.0))
    step = max(1, int(round(sfreq / 50.0)))
    waveforms = [
        [float(v) for v in sources[i, :n_keep:step]] for i in range(sources.shape[0])
    ]
    spectra: dict[str, Any] = {"freqs": [], "psd": []}
    try:
        spectra = _component_spectra(sources, sfreq)
    except Exception:  # noqa: BLE001
        pass

    return {
        "n_components": int(ica.n_components_),
        "contributions": [float(x) for x in fractions],
        "suggested_exclude": [int(i) for i in eog_indices],
        "ch_names": list(raw.ch_names),
        "maps": maps,
        "positions": _channel_xy(fit_raw),
        "waveforms": waveforms,
        "spectra": spectra,
        "sfreq": float(sfreq / step),
    }


def erp_averages(epochs_path: str) -> dict[str, Any]:
    """Grand-average ERP per event id from an epoched FIF."""
    import mne

    epochs = mne.read_epochs(epochs_path, preload=True, verbose="ERROR")
    times = epochs.times.tolist()
    averages: dict[str, list[float]] = {}
    for name in epochs.event_id:
        evoked = epochs[name].average()
        data = evoked.data.mean(axis=0)
        averages[str(name)] = [float(v) for v in data.tolist()]
    return {
        "times": [float(t) for t in times],
        "averages": averages,
        "ch_names": list(epochs.ch_names),
        "n_epochs": int(len(epochs)),
        "event_id": {str(k): int(v) for k, v in epochs.event_id.items()},
    }


def channel_spectra(path: str, *, fmax: float = 40.0) -> dict[str, Any]:
    """Welch PSD per channel for Plot → Spectra (EEGLAB spectopo-like)."""
    import mne
    from scipy.signal import welch

    p = Path(path)
    try:
        raw = mne.io.read_raw(str(p), preload=True, verbose="ERROR")
        data = raw.get_data()
        sfreq = float(raw.info["sfreq"])
        ch_names = list(raw.ch_names)
        # Cap duration for speed.
        n_max = int(min(data.shape[1], sfreq * 60.0))
        data = data[:, :n_max]
    except Exception:
        epochs = mne.read_epochs(str(p), preload=True, verbose="ERROR")
        data = epochs.get_data().mean(axis=0)  # average across epochs for spectra
        sfreq = float(epochs.info["sfreq"])
        ch_names = list(epochs.ch_names)

    channels: dict[str, list[float]] = {}
    freqs_out: list[float] = []
    for i, name in enumerate(ch_names[:32]):
        f, pxx = welch(data[i], fs=sfreq, nperseg=min(256, data.shape[1]))
        mask = f <= fmax
        if not freqs_out:
            step = max(1, int(mask.sum() // 64))
            freqs_out = [float(v) for v in f[mask][::step]]
            step_use = step
        else:
            step_use = max(1, int(mask.sum() // 64))
        band = 10.0 * np.log10(np.maximum(pxx[mask][::step_use], 1e-20))
        channels[str(name)] = [float(v) for v in band]
    return {"freqs": freqs_out, "channels": channels}


def erp_image_data(
    epochs_path: str, *, channel: str | None = None, max_trials: int = 200
) -> dict[str, Any]:
    """Single-channel ERP image (trials × time) for Plot → ERP image."""
    import mne

    epochs = mne.read_epochs(epochs_path, preload=True, verbose="ERROR")
    if len(epochs) == 0:
        return {"trials": [], "times": [], "channel": "", "title": ""}
    ch = channel
    if ch is None or ch not in epochs.ch_names:
        # Prefer Cz-like, else middle channel.
        for cand in ("Cz", "CZ", "Cz-Avg", "CPz", "Pz"):
            if cand in epochs.ch_names:
                ch = cand
                break
        else:
            ch = epochs.ch_names[len(epochs.ch_names) // 2]
    idx = epochs.ch_names.index(ch)
    X = epochs.get_data(copy=False)[:, idx, :]
    if X.shape[0] > max_trials:
        X = X[:max_trials]
    step = max(1, X.shape[1] // 256)
    times = [float(t) for t in epochs.times[::step]]
    trials = [[float(v) for v in row[::step]] for row in X]
    return {
        "trials": trials,
        "times": times,
        "channel": str(ch),
        "title": f"Single-trial ERPs at {ch}",
    }


def augment_preview_pairs(
    epochs_path: str,
    *,
    method: str = "noise",
    noise_std: float = 0.05,
    seed: int = 42,
    max_pairs: int = 6,
) -> dict[str, Any]:
    """Return before/after trial pairs for researcher review (downsampled arrays)."""
    import mne

    epochs = mne.read_epochs(epochs_path, preload=True, verbose="ERROR")
    if len(epochs) == 0:
        return {"pairs": [], "times": []}

    rng = np.random.default_rng(seed)
    X = epochs.get_data(copy=True)
    id_to_name = {int(v): str(k) for k, v in epochs.event_id.items()}
    pairs: list[dict[str, Any]] = []
    n = min(len(epochs), max_pairs)
    indices = rng.choice(len(epochs), size=n, replace=False)

    n_times = X.shape[2]
    step = max(1, n_times // 128)
    times = epochs.times[::step].tolist()

    for idx in indices:
        src = np.array(X[int(idx)], copy=True)
        synth = np.array(src, copy=True)
        if method == "noise":
            ch_std = np.std(synth, axis=1, keepdims=True)
            ch_std = np.where(ch_std < 1e-12, 1.0, ch_std)
            synth = synth + rng.normal(0.0, noise_std, size=synth.shape) * ch_std
        elif method == "time_shift":
            shift = int(rng.integers(-max(1, n_times // 20), max(2, n_times // 20)))
            synth = np.roll(synth, shift, axis=1)
        else:
            n_drop = max(1, int(round(0.1 * synth.shape[0])))
            drop = rng.choice(synth.shape[0], size=n_drop, replace=False)
            synth[drop, :] = 0.0

        code = int(epochs.events[int(idx), 2])
        pairs.append(
            {
                "index": int(idx),
                "class": id_to_name.get(code, str(code)),
                "before": src.mean(axis=0)[::step].astype(float).tolist(),
                "after": synth.mean(axis=0)[::step].astype(float).tolist(),
            }
        )

    return {"pairs": pairs, "times": [float(t) for t in times], "method": method}

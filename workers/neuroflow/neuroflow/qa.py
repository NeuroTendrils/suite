"""QA helpers: ICA component summary, ERP averages, augment before/after pairs.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from typing import Any

import numpy as np


def ica_component_summary(raw_path: str, *, n_components: float | int = 0.99) -> dict[str, Any]:
    """Fit ICA and return JSON-serializable component contributions (no full mixing)."""
    import mne
    from mne.preprocessing import ICA

    from .repro import ICA_RANDOM_STATE

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

    # Explained variance proxy: mean abs mixing weights per component.
    sources = ica.get_sources(fit_raw).get_data()
    contrib = np.mean(np.abs(sources), axis=1)
    total = float(np.sum(contrib)) or 1.0
    fractions = (contrib / total).tolist()

    eog_indices: list[int] = []
    try:
        eog_indices, _ = ica.find_bads_eog(raw, verbose="ERROR")
    except Exception:  # noqa: BLE001
        eog_indices = []

    return {
        "n_components": int(ica.n_components_),
        "contributions": [float(x) for x in fractions],
        "suggested_exclude": [int(i) for i in eog_indices],
        "ch_names": list(raw.ch_names),
    }


def erp_averages(epochs_path: str) -> dict[str, Any]:
    """Grand-average ERP per event id from an epoched FIF."""
    import mne

    epochs = mne.read_epochs(epochs_path, preload=True, verbose="ERROR")
    times = epochs.times.tolist()
    averages: dict[str, list[list[float]]] = {}
    for name in epochs.event_id:
        evoked = epochs[name].average()
        # Mean across channels for a compact plot; keep per-ch optional later.
        data = evoked.data.mean(axis=0)
        averages[str(name)] = [float(v) for v in data.tolist()]
    return {
        "times": [float(t) for t in times],
        "averages": averages,
        "ch_names": list(epochs.ch_names),
        "n_epochs": int(len(epochs)),
        "event_id": {str(k): int(v) for k, v in epochs.event_id.items()},
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

    # Downsample time for UI.
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

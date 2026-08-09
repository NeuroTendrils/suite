from __future__ import annotations

from typing import Any

from suite_backend.domain.models import Recording
from suite_backend.neuroflow.signal import load_raw_for_recording


def list_ica_components(
    recording: Recording,
    *,
    n_components: int | None = 20,
) -> dict[str, Any]:
    """Fit ICA (MNE) and return utilitarian component summaries."""
    import numpy as np
    from mne.preprocessing import ICA

    raw = load_raw_for_recording(recording)
    raw = raw.copy().filter(l_freq=1.0, h_freq=None, verbose=False)
    n = n_components or min(20, len(raw.ch_names))
    ica = ICA(n_components=n, random_state=97, max_iter="auto")
    ica.fit(raw, verbose=False)

    components = []
    sources = ica.get_sources(raw).get_data()
    for idx in range(ica.n_components_):
        ts = sources[idx]
        # crude spectrum via FFT magnitude
        spectrum = np.abs(np.fft.rfft(ts - ts.mean()))
        freqs = np.fft.rfftfreq(ts.size, d=1.0 / raw.info["sfreq"])
        keep = freqs <= 50
        components.append(
            {
                "index": idx,
                "variance_explained": None,
                "rejected": False,
                "spectrum_freqs": freqs[keep].astype(float).tolist()[:: max(1, keep.sum() // 64)],
                "spectrum_power": spectrum[keep].astype(float).tolist()[:: max(1, keep.sum() // 64)],
                "timeseries_preview": ts[:: max(1, ts.size // 500)].astype(float).tolist(),
            }
        )

    # topo data as sensor values for first few components
    maps = []
    for idx in range(min(8, ica.n_components_)):
        maps.append(
            {
                "index": idx,
                "channels": list(raw.ch_names),
                "weights": ica.get_components()[:, idx].astype(float).tolist(),
            }
        )

    return {
        "recording_id": recording.id,
        "n_components": ica.n_components_,
        "components": components,
        "maps": maps,
    }

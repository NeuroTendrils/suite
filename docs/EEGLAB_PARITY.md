# EEGLAB parity map

Reference: [EEGLAB](https://eeglab.org/) tutorials and the wiki slides attached in product planning (import → reject → ICA → plot → STUDY).

NeuroTendrils is a Qt/Python Raw→Ready pipeline. This document records what we built against EEGLAB concepts, and what is still out of scope.

## Workflow mapping

| EEGLAB (menu / tool) | NeuroTendrils | Status |
|---|---|---|
| File → Import data | NeuroFlow **Recording** (EDF/BDF/FIF/SET/BrainVision/CNT/GDF/TXT) | Done |
| Edit → Channel locations | Inspect **Apply montage** + Plot hub **Channels** | Done (standard montages) |
| Plot → Channel data (scroll) | Inspect **EegViewer** (scroll, amp, window) | Done |
| Tools → Reject continuous data by eye | Inspect **Paint bad** + Save BAD marks | Done |
| Edit → Select data / drop channels | Inspect channel list → **Drop selected channels** | Done |
| Edit → Event values / labels | Inspect **Trial labels** + dataset manifest events | Partial |
| Tools → Filter / reref / resample | NeuroFlow **Plan** steps | Done (recipe) |
| Tools → Extract epochs | Plan `event_epoch` / `epoch` | Done |
| Tools → Run ICA | Plan `ica` step (writes `ica.fif` + `ica_summary.json`) | Done |
| Tools → Reject components by map (`pop_selectcomps`) | Review **Plot → ICA maps** (topo grid, red/green headers) | Done |
| Plot → Component properties (`pop_prop`) | ICA map **Properties** (topo + waveform + PSD) | Done |
| Plot → Channel spectra and maps (`spectopo`) | Review **Plot → Spectra** (PSD lines; topo-at-freq later) | Partial |
| Plot → Channel ERPs | Review **Plot → ERP** | Done |
| Plot → Channel ERP image | Review **Plot → ERP image** | Done |
| Plot → ERP map series (2D/3D) | — | Not yet |
| Plot → Component ERPs / spectra / time-frequency | Properties PSD + waveforms; ERSP/ITC later | Partial |
| Tools → DIPFIT / eLoreta | — | Not yet |
| File → Create STUDY | Project = Study; dataset.json multi-subject | Partial |
| Study → designs / precompute / cluster | Clusters scaffold only | Not yet |
| Data augmentation (suggested trials) | Plan `augment` + Review before/after | Done (NeuroFlow, not EEGLAB) |
| Train / infer models | NeuroStudio | Done (beyond EEGLAB) |

## Where to click in the app

1. **NeuroFlow → Recording** — import a file (TXT becomes FIF).
2. **Inspect** — scroll traces, paint BAD, apply montage, drop channels, map labels; **Channels** tab shows layout.
3. **Fingerprint → Plan → Run** — automated filter/notch/reref/resample/ICA/epoch/augment.
4. **Review** — **Plot hub** tabs:
   - **Channels** — electrode layout topo
   - **Spectra** — multi-channel PSD
   - **ERP** — grand averages by event
   - **ERP image** — trials × time + average
   - **ICA maps** — reject-by-map (toggle header red = exclude); double-click for properties
5. **Apply ICA exclude to plan** — writes exclude indices into the ICA step; re-run to apply.
6. **Train in NeuroStudio** — model training on cleaned epochs.

## Artifacts written by a run

Under each run folder (e.g. `runs/<name>/`):

| File | Purpose |
|---|---|
| `cleaned.fif` / `cleaned-epo.fif` | Cleaned continuous or epoched output |
| `ica.fif` | Fitted ICA solution (MNE) |
| `ica_summary.json` | Maps, contributions, waveforms, spectra, suggested exclude, channel XY |
| `run.json` | Plan + reproducibility metadata |

Review loads `ica_summary.json` when present so ICA maps appear **without refitting**.

## Implementation notes (what we did)

- **Widgets** (QPainter, no matplotlib): `topoplot.py`, `ica_maps.py`, `spectra_plot.py`, `erp_image.py`, `plot_hub.py`.
- **NeuroFlow apply**: ICA step persists maps/spectra/waveforms into `ica_summary.json`.
- **QA helpers** (`neuroflow/qa.py`): `ica_component_summary`, `channel_spectra`, `erp_averages`, `erp_image_data`, `augment_preview_pairs`.
- **Jobs**: preview / review / montage / drop-channels run off the GUI thread; JSON/signal sanitization via `jsonutil.py`.
- **Launch**: `pip install -e .` then `python -m neurotendrils`.

## Explicitly deferred (EEGLAB depth)

- 3D head ERP map series  
- Linked spectopo topomaps at peak frequencies  
- Component ERSP / ITC time-frequency  
- DIPFIT / eLoreta source localization  
- Full STUDY designs, precompute measures, PCA clustering UI  
- ICLabel classifier  

These remain tracked product work; the Plot hub and ICA reject-by-map are the first EEGLAB-shaped visualization surface in-app.

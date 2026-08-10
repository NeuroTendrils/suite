# User guide (utilitarian)

Local EEG research workflow in NeuroTendrils Suite. UI is intentionally plain.

## 1. Create a study

1. Launch the desktop app (`apps/desktop`).
2. Enter a study name → **Create study**.
3. Add a subject (e.g. `S001`) if prompted / via manager.

## 2. Import EEG

1. **Import** tab → Browse a file (`.fif`, `.edf`, `.set`, `.txt`, …).
2. If status is `needs_config`, set **sfreq** (and MAT `data_key`) — Suite will not guess.
3. **Import recording**. Canonical FIF lands under study artifacts; raw source is never overwritten.

## 3. Optional: attach other modalities

Use stream import (gyro/accel/ECG/…) with explicit modality + sfreq. Attach to the same recording when possible.

## 4. Sync + validate

- **Sync**: create a SyncGroup (shared triggers / timestamps / manual offset). Do not assume streams are aligned.
- **Validate**: run recording/study checks; multi-stream without sync warns.

## 5. Visualizer (NeuroFlow)

Open **Visualizer** with a recording selected.

| Mode | What to do |
|------|------------|
| **Signal** | Drag bad segments · click channel to toggle bad/good · click red band to unreject · **REJECT** · optional Clean continuous / Montage |
| **ICA** | Fit FastICA · click ICs to reject/keep · **Apply removals → new FIF** |
| **ERP** | Compute butterfly / channel ERP + ERPimage |
| **Epochs** | Create epochs · click trials · **REJECT** toggles reject↔keep |

## 6. Preprocess plan

**Preprocess** → default plan (filter 1–40 → notch 60 → average reref) → Execute. Interactive reject/ICA stay in Visualizer.

## 7. Features + analysis

- **Features**: band power / PSD.
- **Analysis**: descriptive stats on features, or condition comparison on epochs.

## 8. ML path (NeuroStudio)

Typical order on **Dataset** → **Studio** → **Report** → **Export**:

1. **Build from epochs** (needs ≥2 conditions for classification).
2. **Create subject/trial split** (single-subject trials warn about leakage).
3. **Recommend template** (always EEGNet placeholder today).
4. **Create experiment** (links dataset + split).
5. **Train** (sklearn LogisticRegression on tabular features — not Braindecode yet).
6. **Eval** / **Explain** / **Infer**.
7. **Report** markdown; **Export** study package or model bundle.

## Provenance reminders

- REJECT writes annotations/decisions (or clean FIF siblings) — source import stays intact.
- ICA apply / clean continuous promote a **working** FIF for viewing/downstream.
- Prefer subject-wise splits when you have multiple subjects.

## Troubleshooting

| Symptom | Likely fix |
|---------|------------|
| Import blocked | Fill required_config from inspect |
| No events / ERP empty | Use `.set` or add events; `.txt` stim columns should extract |
| Train errors “<2 classes” | Build dataset from multi-condition epochs |
| Command not allowlisted | Rebuild desktop after IPC allowlist change |
| ICA missing sklearn | `pip install scikit-learn` in the backend env |

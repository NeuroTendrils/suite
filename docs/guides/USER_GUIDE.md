# User guide (utilitarian)

Local EEG research workflow in NeuroTendrils Suite. UI is intentionally plain.

## App layout

| Area | Purpose |
|------|---------|
| **Home** | Create/select studies, see subjects, recordings, validation and model progress, and the suggested next step. |
| **NeuroFlow** | Per-recording work: Import → Inspect → Preprocess → Analyze. |
| **NeuroStudio** | Per-study ML: Dataset → Train → Report & export. |

The top bar shows the active study and recording (click the recording to inspect it), the backend connection
state, and any running operation with elapsed time. Only one operation runs at a time; its buttons are disabled
while it runs. Disabled actions explain why next to them.

Workflow steps show their state: ✓ done (the step's output exists in the study), numbered (available), lock
(not available yet — hover for what is missing), spinner (running). NeuroStudio's **Before you train** checklist
shows the same prerequisites explicitly.

Errors appear in a banner with a suggested fix and **Technical details** for the raw message; they stay until
dismissed. Confirmations fade after a few seconds. The **Activity** drawer at the bottom lists every operation of
the session with time, outcome, and expandable details (filter to failures, copy, clear).

Keyboard: the first Tab stop is **Skip to content**; recording rows open with Enter; the plot tabs in Inspect move
with the arrow keys.

## 1. Create a study

1. Launch the desktop app (`apps/desktop`).
2. **Home → New study**. Enter a name (required) and optional task → **Create study**.
3. Add subjects in the **Subjects** card (label + optional JSON metadata), or create one while importing.

## 2. Import EEG

1. **Import recording** (Home) or **NeuroFlow → Import**. Browse a file (`.fif`, `.edf`, `.set`, `.txt`, …); it is inspected automatically.
2. If the format needs settings, enter the **Sampling rate (Hz)** (and MAT variable) — there is no default; Suite will not guess.
3. Choose the subject (or **New subject…**) → **Import recording**. Canonical FIF lands under study artifacts; raw source is never overwritten.

## 3. Optional: attach other modalities

Use stream import (gyro/accel/ECG/…) with explicit modality + sfreq. Attach to the same recording when possible.

## 4. Sync + validate

- **Sync**: create a SyncGroup (shared triggers / timestamps / manual offset). Do not assume streams are aligned.
- **Validate**: run recording/study checks; multi-stream without sync warns.

## 5. Visualizer (NeuroFlow)

Open **NeuroFlow → Inspect** with a recording selected (or click a recording on Home).
Marks are pending until you apply them; switching recording or study with pending marks asks for confirmation.

| Mode | What to do |
|------|------------|
| **Signal** | Drag bad segments · click channel to toggle bad/good · click red band to unreject · **REJECT** · optional Clean continuous / Montage |
| **ICA** | Fit FastICA · click ICs to reject/keep · **Apply removals → new FIF** |
| **ERP** | Compute butterfly / channel ERP + ERPimage |
| **Epochs** | Create epochs · click trials · **REJECT** toggles reject↔keep |

## 6. Preprocess plan

**NeuroFlow → Preprocess** → **Create default plan** (filter → notch → average reref) → pick it in **Plan** → **Run on this recording**. Interactive reject/ICA stay in Inspect.

## 7. Features + analysis

- **Features**: band power / PSD.
- **Analysis**: descriptive stats on features, or condition comparison on epochs.

## 8. ML path (NeuroStudio)

Typical order in **NeuroStudio**: **Dataset** → **Train** → **Report & export**:

1. **Build dataset** from a chosen epoch set (needs ≥2 conditions for classification).
2. **Create split** for the selected dataset: method, validation/test fractions, and seed are shown and editable (defaults 0.15 / 0.2 / 0). Single-subject trial splits are flagged for leakage.
3. **Recommend template** (always EEGNet placeholder today).
4. **Create experiment** from the selected dataset + split.
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

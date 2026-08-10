# Pipeline phases (1–25)

Study-centric multimodal research OS. After each phase: smoke → commit.

| Phase | Name | Status |
|------:|------|--------|
| 1 | Study structure (DataStream + CRUD + migrator) | done |
| 2 | EEG import | done |
| 3 | External modality import | done |
| 4 | Normalize common representation | done |
| 5 | Synchronization | done |
| 6 | Validation | done |
| 7 | Subject/session manager | done |
| 8 | Timeline viewer | done |
| 8a | Artifact rejection | done |
| 9 | Channel/data management | done |
| 10 | Events/annotations | done |
| 11 | NeuroFlow preprocessing | done |
| 12 | Epochs/trials | done |
| 13 | Feature extraction | done |
| 14 | Analysis/statistics | done |
| 15 | ML dataset builder | done |
| 16 | Leakage-safe splits | done |
| 17 | ML training (+ EEGNet placeholder recommend) | done |
| 18 | Model evaluation | done |
| 19 | Multimodal AI | done |
| 20 | Explainability | done |
| 21 | Experiment tracking | done |
| 22 | Inference | done |
| 23 | Results/reporting | done |
| 24 | Save/export | done |
| 25 | Detailed documentation | done |

See also: [architecture overview](../architecture/OVERVIEW.md), [IPC reference](../reference/IPC.md), [user guide](../guides/USER_GUIDE.md), [developer guide](../guides/DEVELOPER.md).

## Phase 1 notes

- `Study.schema_version = 2`
- `DataStream` stored under `workspace/studies/{id}/streams/`
- IPC: `studies.tree`, `subjects.set_metadata`, `sessions.add`, `runs.add`, `streams.list`, `streams.get`
- v1 studies auto-migrate on open (legacy channels → EEG stream)
- NeuroStudio `templates.recommend` always returns EEGNet placeholder
- UI: utilitarian Study structure browser (no EEGLAB chrome)

## Phase 2 notes

- Self-describing (ready): FIF, EDF, BDF, GDF, BrainVision `.vhdr`, EEGLAB `.set`, Neuroscan `.cnt`
- Ambiguous (`needs_config`): TXT/CSV/TSV/ASC (requires `sfreq`), MAT (requires `data_key` + `sfreq`)
- `import.recording` refuses missing required_config — no silent guesses
- MNE imports write canonical FIF into study artifacts when imported
- UI: Browse → inspect status → config fields when needed → Import

## Phase 3 notes

- IPC: `import.stream.inspect`, `import.stream`
- Modalities: gyro, accel, ECG, EMG, EOG, eye, motion, behavioral, trigger, GSR, respiration, misc
- Required: explicit `modality` + `sfreq` (or timestamp column); filename suggestion is hint only
- Samples stored as `streams/samples/{stream_id}_data.npy` (+ optional times)
- Attach to existing `recording_id` or create a new recording shell

## Phase 4 notes

- `scientific/io/canonical.py`: `load_stream_samples`, `load_primary_eeg_raw`, `normalize_recording`
- Imports auto-run normalize; IPC `recordings.normalize` for re-run
- Signal/ERP/ICA/plans load via canonical FIF / NPY paths (not vendor path first)
- `recordings.signal_window` accepts optional `stream_id` for any modality

## Phase 5 notes

- `SyncGroup` / `SyncLink` / `SyncMethod`; never `assumed_synchronized=True` from start-time similarity
- Methods: shared_triggers, timestamps, manual_offset, unspecified (fallback)
- IPC: `sync.create`, `sync.list`, `sync.get`, `sync.set_offset`
- Stored under `workspace/studies/{id}/sync/`

## Phase 6 notes

- `scientific/io/validate.py`: stream / recording / study reports
- Warns on multi-stream without SyncGroup; blocks invalid sync assumptions
- IPC: `validate.stream`, `validate.recording`, `validate.study`
- Recording.validation summary persisted

## Phase 7 notes

- IPC: `studies.manager` — subject/session tree with modalities, sync, validation rollups
- UI: sidebar manager + Import/Sync/Validate/Timeline tabs (utilitarian)

## Phase 8 notes

- `neuroflow/timeline.py` + IPC `recordings.timeline`
- Applies SyncGroup offsets onto a shared reference timeline
- UI: utilitarian multimodal sparkline viewer + event list

## Phase 8a notes

- Heuristic `detect_artifacts` (std / PTP); never mutates raw
- IPC: `artifacts.detect/apply/list/revert` → Annotation + HumanDecision masks
- UI: Visualizer reject (drag + REJECT); masks only

## Phase 9 notes

- IPC: `channels.list/update/reorder/apply_montage` (stream-owned, decisions for reversibility)
- UI: Visualizer channel click + Channels ops

## Phase 10 notes

- IPC: `events.list/create/delete`, `annotations.list/delete` (+ existing create)
- Study `event_definitions` mapped on list
- UI: Events tab

## Phase 11 notes

- `plans.default` EEGLAB-tutorial-aligned placeholder (filter 1–40 → notch 60 → average reref)
- Interactive after plan: Visualizer reject / ICA (FastICA+sklearn) / Epochs / ERP
- Executor ops: `mark_bad_channels`, `interpolate_bads`
- UI: Preprocess tab + Visualizer

## Phase 12 notes

- Domain: `EpochSet` / `Trial` with subject/session/condition/stream refs
- IPC: `epochs.create/list/get/reject`; optional FIF under `epochs/`
- UI: Epochs tab + Visualizer Epochs mode

## Phase 13 notes

- Domain: `FeatureSet` with provenance + CSV export hooks
- IPC: `features.extract/list/get` (`band_power`, `psd`, connectivity placeholder)
- UI: Features tab

## Phase 14 notes

- Domain: `AnalysisReport`
- IPC: `analysis.run/list/get` — descriptive feature stats; Welch-style condition compare on epochs
- UI: Analysis tab
- Tests: `test_phase_14_analysis.py`

## Phase 15 notes

- Domain: `MLDataset` with `X.npy` / `y.npy` paths
- IPC: `datasets.build/list/get` — per-trial band-power from epoch FIF
- UI: Dataset tab
- Tests: `test_phase_15_datasets.py`

## Phase 16 notes

- Domain: `DataSplit`
- IPC: `datasets.splits.create/list` — subject-wise or stratified trial; `neurostudio.leakage.check`
- Single-subject fallback warns about subject leakage
- Tests: `test_phase_16_splits.py`

## Phase 17 notes

- `neurostudio.train.start` fits sklearn `LogisticRegression` (+ scaler) on MLDataset
- EEGNet remains **recommend-only** placeholder (`templates.recommend`)
- Persists `ModelRecord` joblib under `models/`
- Tests: `test_phase_17_training.py`

## Phase 18 notes

- `neurostudio.eval.run` → accuracy, macro-F1, confusion matrix; `Result` persisted
- Tests: `test_phase_18_eval.py`

## Phase 19 notes

- `datasets.build` `source=multimodal` fuses EEG trial features with external stream window mean/std
- Tests: `test_phase_19_multimodal.py`

## Phase 20 notes

- `neurostudio.explain.run` — coefficient magnitudes + permutation importance
- Tests: `test_phase_20_explain.py`

## Phase 21 notes

- `neurostudio.experiments.list/get` (+ create)
- Repository helpers for experiments/models/results
- Tests: `test_phase_21_tracking.py`

## Phase 22 notes

- `neurostudio.infer.run` → labels (+ optional proba); `Prediction` JSON under `results/`
- Tests: `test_phase_22_infer.py`

## Phase 23 notes

- `neurostudio.report.build` → markdown study summary or experiment report under `reports/`
- Tests: `test_phase_23_report.py`

## Phase 24 notes

- `study.export` zip (metadata by default); `neurostudio.model.export` model+manifest zip
- Tests: `test_phase_24_export.py`

## Phase 25 notes

- Expanded docs under `docs/`: architecture, IPC reference, user guide, developer guide
- This PHASES.md is the authoritative phase checklist

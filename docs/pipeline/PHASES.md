# Pipeline phases (1–24)

Study-centric multimodal research OS. After each phase: review → approve → commit.

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
| 14 | Analysis/statistics | pending |
| 15 | ML dataset builder | pending |
| 16 | Leakage-safe splits | pending |
| 17 | ML training (+ EEGNet placeholder recommend) | pending (placeholder recommender landed early) |
| 18 | Model evaluation | pending |
| 19 | Multimodal AI | pending |
| 20 | Explainability | pending |
| 21 | Experiment tracking | pending |
| 22 | Inference | pending |
| 23 | Results/reporting | pending |
| 24 | Save/export | pending |

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
- UI: Reject tab

## Phase 9 notes

- IPC: `channels.list/update/reorder/apply_montage` (stream-owned, decisions for reversibility)
- UI: Channels tab

## Phase 10 notes

- IPC: `events.list/create/delete`, `annotations.list/delete` (+ existing create)
- Study `event_definitions` mapped on list
- UI: Events tab

## Phase 11 notes

- `plans.default` fixed placeholder plan (filter→notch→reref); not data-adaptive
- Executor ops: `mark_bad_channels`, `interpolate_bads`
- `neuroflow.recommend_preprocessing` returns same placeholder plan
- UI: Preprocess tab

## Phase 12 notes

- Domain: `EpochSet` / `Trial` with subject/session/condition/stream refs
- IPC: `epochs.create/list/get`; optional FIF under `epochs/`
- UI: Epochs tab

## Phase 13 notes

- Domain: `FeatureSet` with provenance + CSV export hooks
- IPC: `features.extract/list/get` (`band_power`, `psd`, connectivity placeholder)
- UI: Features tab

# Pipeline phases (1–24)

Study-centric multimodal research OS. After each phase: review → approve → commit.

| Phase | Name | Status |
|------:|------|--------|
| 1 | Study structure (DataStream + CRUD + migrator) | done |
| 2 | EEG import | done |
| 3 | External modality import | done |
| 4 | Normalize common representation | done |
| 5 | Synchronization | done |
| 6 | Validation | pending |
| 7 | Subject/session manager | pending |
| 8 | Timeline viewer | pending |
| 8a | Artifact rejection | pending |
| 9 | Channel/data management | pending |
| 10 | Events/annotations | pending |
| 11 | NeuroFlow preprocessing | pending |
| 12 | Epochs/trials | pending |
| 13 | Feature extraction | pending |
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

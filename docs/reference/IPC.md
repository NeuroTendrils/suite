# IPC command reference

All commands are allowlisted in `apps/desktop/src-tauri/src/lib.rs` and registered on `REGISTRY` in Python.

Request shape: `{ "id": "...", "command": "namespace.action", "params": { ... } }`.

## Core / workspace

| Command | Purpose |
|---------|---------|
| `health` | Liveness |
| `workspace.info` | Workspace path + command allowlist |
| `commands.list` | Registered commands |

## Study structure

| Command | Purpose |
|---------|---------|
| `studies.create/list/get/tree/manager/inspect` | Study CRUD + manager rollup |
| `subjects.add` / `subjects.set_metadata` | Subjects |
| `sessions.add` / `runs.add` | Sessions / runs |
| `streams.list` / `streams.get` | DataStreams |
| `studies.set_event_map` / `studies.set_visibility` | Study maps / visibility |

## Import / recordings

| Command | Purpose |
|---------|---------|
| `import.inspect` | Format inspect (self-describing vs needs_config) |
| `import.recording` | EEG import → Recording + artifact FIF |
| `import.stream.inspect` / `import.stream` | External modality streams |
| `recordings.get/inspect/normalize` | Recording metadata / normalize |
| `recordings.signal_window` | Sample window (any stream_id) |
| `recordings.timeline` | Multimodal timeline + sync offsets |

## Sync / validate

| Command | Purpose |
|---------|---------|
| `sync.create/list/get/set_offset` | SyncGroup alignment |
| `validate.stream/recording/study` | Validation reports |

## NeuroFlow (reject / channels / events / plans)

| Command | Purpose |
|---------|---------|
| `artifacts.detect/apply/list/revert` | Artifact masks (never raw) |
| `channels.list/update/reorder/apply_montage` / `channels.set_bad` | Channel ops |
| `events.list/create/delete` | Events |
| `annotations.create/list/delete` | Annotations |
| `plans.create/list/get/default/execute` | Preprocessing plans |
| `neuroflow.recommend_preprocessing` | Placeholder recommender |
| `neuroflow.detect_artifacts` / `detect_lab_interference` | Heuristics |
| `neuroflow.clean_continuous` | Amplitude window drop → new FIF |
| `ica.components.list` / `ica.component.set_rejection` / `ica.apply` | FastICA |
| `erp.compute` | Channel ERPs + ERPimage |
| `epochs.create/list/get/reject` | EpochSet / Trial |
| `features.extract/list/get` | Band power / PSD |
| `analysis.run/list/get` | Descriptive / condition compare |
| `augmentation.run` | Augmentation stub |

## NeuroStudio / datasets / export

| Command | Purpose |
|---------|---------|
| `datasets.build/list/get` | MLDataset from epochs / features / multimodal |
| `datasets.splits.create/list` | Leakage-aware splits |
| `neurostudio.templates.list/get/recommend` | Templates; recommend → EEGNet |
| `neurostudio.experiments.create/list/get` | Experiment tracking |
| `neurostudio.train.start` | sklearn LogReg train |
| `neurostudio.hypertune.start` | Hypertune stub |
| `neurostudio.eval.run` | Accuracy / F1 / confusion |
| `neurostudio.generalization.run` | Test-split eval proxy |
| `neurostudio.explain.run` | Coef + permutation importance |
| `neurostudio.infer.run` | Predict + Prediction record; `split`: `all` (default) / `train` / `val` / `test`; returns labels, proba, confidence, true_labels, indices |
| `neurostudio.report.build` | Markdown reports |
| `neurostudio.model.export` | Model zip bundle |
| `neurostudio.leakage.check` | Subject overlap check |
| `study.export` | Study zip package |

## Allowlist rule

If a command works in Python tests but fails from the desktop app with `command not allowlisted`, add the string to `allowlisted_commands()` in `lib.rs` and rebuild Tauri.

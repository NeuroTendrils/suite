# Architecture overview

NeuroTendrils Suite is a **local-first, multi-subject EEG research OS** — not an EEGLAB clone. Hierarchy:

```text
Study → Subject → Session → Run → Recording → DataStream(s)
```

## Runtime

| Layer | Role |
|-------|------|
| **Tauri (Rust)** | Window, process lifecycle, **allowlisted** `suite_call` only |
| **React (TypeScript)** | Utilitarian UI — no scientific logic in the renderer |
| **Python `suite_backend`** | Domain, NeuroFlow, NeuroStudio, MNE / sklearn I/O |

IPC is a private Unix domain socket (a named pipe on Windows). JSON request/response lines with Pydantic schemas. No free-form code execution from the UI.

## Product modules

| Module | Role |
|--------|------|
| **NeuroFlow** | Import, sync, validate, visualize, reject, plans, ICA, ERP, epochs, features, analysis |
| **NeuroStudio** | Datasets, splits, templates (EEGNet recommend placeholder), train/eval/infer/explain/report/export |
| **Hub / Teams** | Future cloud; `visibility` / quota interfaces only today |

## Science stack

- **MNE-Python** — I/O, filtering, ICA (FastICA via scikit-learn), epochs, ERP
- **scikit-learn** — ICA peer dep + utilitarian ML train/eval/explain
- **Braindecode** — optional (`pip install suite-backend[ml]`); templates catalogued; **training not wired** (recommend always EEGNet)

## Provenance rules

1. **Never mutate source raw files.**
2. Processing writes immutable artifacts (`DatasetArtifact`, FIF derivatives, joblib models) with parent links, parameters, checksums where applicable.
3. Human judgment is stored as `Annotation` + `HumanDecision` (reject masks, ICA keep/reject, epoch reject).
4. Working FIF for visualization may be **promoted** via `DataStream.sample_paths["fif"]` while `fif_original` / import sources remain.

## Workspace layout

```text
workspace/studies/{study_id}/
  study.json
  streams/ (+ samples/)
  sync/
  epochs/
  features/
  datasets/ (+ arrays/)
  plans/
  artifacts/
  experiments/
  models/
  results/
  reports/
  exports/
  logs/
```

## UI surface (desktop)

Tabs: Import · Visualizer · Sync · Validate · Events · Preprocess · Epochs · Features · Analysis · Dataset · Studio · Report · Export.

Visualizer modes: Signal · ICA · ERP · Epochs.

## Related docs

- [Pipeline phases](../pipeline/PHASES.md)
- [IPC command reference](../reference/IPC.md)
- [User guide](../guides/USER_GUIDE.md)
- [Developer guide](../guides/DEVELOPER.md)

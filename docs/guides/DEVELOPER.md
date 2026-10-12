# Developer guide

## Repo layout

```text
apps/desktop/          Tauri + React UI
backend/src/suite_backend/
  domain/              Pydantic models
  ipc/handlers/        Thin IPC adapters
  neuroflow/           Preprocessing / timeline / ICA / ERP
  neurostudio/         ML train/eval/infer/explain/export/report
  scientific/          Algorithms + I/O (MNE)
  storage/             Local workspace repository
docs/                  Architecture, phases, guides, IPC
```

## Setup

```bash
cd /path/to/suite
python3 -m venv .venv && . .venv/bin/activate
pip install -e "backend[dev]"
# optional Braindecode/torch:
# pip install -e "backend[ml]"

cd apps/desktop
npm install
npm run tauri:dev
```

Backend smoke tests:

```bash
. .venv/bin/activate
cd backend
pytest -q
```

## Adding an IPC command

1. Implement logic under `neuroflow/`, `neurostudio/`, or `scientific/algorithms/`.
2. Add `@REGISTRY.register("namespace.action", ParamsModel)` in `ipc/handlers/*_cmds.py`.
3. Import the handler module from `ipc/handlers/__init__.py`.
4. Add the command string to `allowlisted_commands()` in `apps/desktop/src-tauri/src/lib.rs`.
5. Wire the control in the page for its step (`apps/desktop/src/pages/…`), with any state/action in the matching hook (`apps/desktop/src/hooks/…`) via `runFlow` / `studioRun` / `exec`. See *Desktop frontend layout* below.
6. Add `backend/tests/test_phase_NN_*.py` calling the handler function directly with `AppContext(tmp_path)`.
7. Document in `docs/pipeline/PHASES.md` + `docs/reference/IPC.md`.
8. Commit: `feat(<area>): Phase N <why>`.

## Desktop frontend layout

`apps/desktop/src/`:

| Path | Responsibility |
|------|----------------|
| `App.tsx` | Composition root: page/step navigation, wiring hooks to pages, layout. |
| `hooks/useOperations.ts` | The single running task (duplicate-click guard), notices, activity log. |
| `hooks/useStudySession.ts` | Connection, study list, active study/manager, active recording, refresh. |
| `hooks/useStudyLists.ts` | Read-only lists (epochs, plans, datasets, splits, experiments…) for the current page. |
| `hooks/useResults.ts` | Latest command replies (`runFlow`, `studioRun`), cleared per study/recording. |
| `hooks/useImport.ts`, `useInspector.ts`, `usePreprocess.ts` | NeuroFlow Import / Inspect (pending marks, ICA, ERP, epochs) / Preprocess state + actions. |
| `hooks/useNeuroStudio.ts` | Dataset/split/experiment selection and actions. |
| `hooks/useStudyForms.ts`, `usePreferences.ts` | New-study and subject forms; theme and rail preferences. |
| `pages/home`, `pages/flow`, `pages/studio` | One component per page / workflow step. |
| `components/layout.tsx` | Rail, top bar, module header + step indicator, step footer. |
| `components/plots.tsx`, `tables.tsx`, `ui.tsx` | EEG/ERP plots, shared tables, small UI building blocks. |
| `lib/` | Pure helpers: `backend.ts` (`exec`: treats `{status:"error"}` replies as failures), `workflow.ts` (step states, Back/Next), `study.ts`, `errors.ts`, `constants.ts` (fixed processing parameters — do not change in UI work). |

Workflow state lives in hooks called from `App`, not inside page components, so pending marks and half-filled forms survive moving between pages and steps.

Frontend checks (from `apps/desktop`):

```bash
npm run typecheck   # app + tests
npm run lint
npm test            # node --test (pure helpers) + vitest (UI interaction tests, jsdom)
npm run build
```

UI tests (`tests/ui/*.test.tsx`) render the real `App` against an in-memory fake backend (`tests/ui/fakeBackend.ts`) that replaces only `suiteCall` and the dialog plugin. Add a fake handler when a test needs a new command.

## Domain persistence patterns

- JSON sidecars under study subdirs via `LocalStudyRepository`.
- Large arrays as `.npy` / `.fif` / `.joblib` with paths recorded on the domain object.
- Prefer appending `HumanDecision` for reversible human actions.

## Testing conventions

- Use `AppContext(tmp_path / "ws")` — no real user workspace.
- Prefer importing FIF via `import_recording` then calling handlers.
- Shared ML seed helper: `backend/tests/_ml_helpers.py` (`seed_two_class_recording`).
- pytest `pythonpath` includes `src` and `.` (see `backend/pyproject.toml`).

## Design invariants

- UI never computes science; it only calls allowlisted IPC.
- No silent format guessing on ambiguous imports.
- No assumed sync without SyncGroup.
- EEGNet recommender is intentionally a **placeholder** until a real model recommender exists.
- sklearn training is the utilitarian default; Braindecode training is future work behind optional deps.

## Documentation map (Phase 25)

| Doc | Audience |
|-----|----------|
| `docs/architecture/OVERVIEW.md` | System shape |
| `docs/pipeline/PHASES.md` | Phase checklist + notes |
| `docs/reference/IPC.md` | Command catalog |
| `docs/guides/USER_GUIDE.md` | Operator workflow |
| `docs/guides/DEVELOPER.md` | This file |

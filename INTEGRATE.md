# Integration guide

Everything here drops into `suite/` and matches the conventions already in the
repo (Pydantic params + `REGISTRY.register`, allowlisted `suiteCall`, per-phase
test files).

## 1. Backend — batch and recipes

```
cp backend/src/suite_backend/neuroflow/batch.py       suite/backend/src/suite_backend/neuroflow/
cp backend/src/suite_backend/ipc/handlers/batch_cmds.py  suite/backend/src/suite_backend/ipc/handlers/
cp backend/tests/test_phase_26_batch.py               suite/backend/tests/
```

Register the new handler module wherever the others are imported — the same
place `neuroflow_cmds` is pulled in (`ipc/handlers/__init__.py`):

```python
from suite_backend.ipc.handlers import batch_cmds  # noqa: F401
```

Then:

```bash
cd suite/backend && python -m pytest tests/test_phase_26_batch.py -q
```

All 15 tests pass against the shipped code.

### New commands

| Command | Purpose |
|---|---|
| `batch.preview` | Resolve scope + eligibility. Writes nothing. |
| `batch.execute` | Apply a plan across the scope, isolated per recording. |
| `recipe.export` | Serialize a plan to a portable JSON document. |
| `recipe.import` | Validate and install a recipe into a study. |

Add all four to the Tauri allowlist in
`apps/desktop/src-tauri/permissions/suite.toml` — they will be rejected
otherwise.

### One thing to confirm on your side

`check_eligibility` skips recordings already derived by the same plan
revision, keyed on `plan.revision`. If `ProcessingPlan` has no `revision`
field yet, add one (an int bumped on every edit) or idempotence degrades to
"skip anything this plan ever touched." A `getattr` fallback is already in
place so nothing crashes either way.

## 2. Frontend — components

```
cp apps/desktop/src/theme.css              suite/apps/desktop/src/
cp apps/desktop/src/components/*           suite/apps/desktop/src/components/
```

Import `theme.css` once, above `App.css`, in `main.tsx`. Then delete the
`:root` / `[data-theme]` blocks at the top of `App.css` — they are now
duplicated and will fight the tokens.

All three components typecheck clean under `strict` with `noUnusedLocals`.

### Splitting App.tsx

`App.tsx` is 2,895 lines. Do it in this order — each step is independently
shippable and none of them require touching the backend:

1. **`SignalCanvas`** — replaces `StackedStreamPlot` and its callers.
   Biggest single win: about 400 lines of render code leave `App.tsx`, and
   the canvas now reads its colors from CSS variables instead of hardcoded
   hex, so light theme works for free.
2. **`LineageRibbon`** — new surface, no code to remove.
3. **`BatchRunner`** — new surface, opens from the Preprocess tab.
4. **`useStudy()` hook** — pull the `studies` / `manager` / `selectedId`
   state and its `refresh` logic out. That is the largest remaining cluster.
5. **`FlowStages` / `StudioStages`** — the stage machinery is already
   data-driven via `FLOW_STAGES`; lifting it into its own component is
   mechanical.

After 1–5, `App.tsx` should be under 600 lines and is mostly routing.

## 3. Wiring the ribbon to real data

The ribbon takes `LineageStep[]`. Build it from artifacts you already store —
each `DatasetArtifact` has `operation`, `parameters`, `parent_id`, and
`created_at`, which is exactly the shape needed:

```ts
const steps: LineageStep[] = artifacts.map((a) => ({
  id: a.id,
  label: LABELS[a.operation] ?? a.operation,
  detail: describeParams(a.operation, a.parameters),
  kind: HUMAN_OPS.has(a.operation) ? "human" : "filter",
  artifactId: a.id,
  at: a.created_at,
}));
```

Scrubbing to step *i* means requesting the signal window from artifact
`steps[i].artifactId` rather than from head. `recordings.signal_window`
already takes a stream; it needs an optional `artifact_id` parameter to
serve an earlier derivative. That is the one backend change the ribbon
needs, and it is small.

## 4. Licensing gap

`suite/README.md` says "Proprietary" but the repo has no LICENSE file, while
`neuroflow/` is AGPL-3.0. Add the license text, and add a CI check so an
AGPL import can never reach `suite/backend/src`:

```bash
! grep -rl "AGPL" suite/backend/src
```

Currently clean — worth keeping that way automatically.

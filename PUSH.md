# Pushing to github.com/NeuroTendrils

Two repos. Do NeuroLearn first — it is a clean new tree with nothing to
conflict against.

## 1. NeuroLearn

The `neurolearn/` folder here is a complete addition to your existing
NeuroLearn repo. It does not touch `app/`, `content/`, `packs/`, or `tools/`.

```powershell
cd ~\Documents\NeuroTendrils\neurolearn
git checkout -b feat/accounts-and-authoring

# copy the new tree in (server/, README, CI, env template, gitignore)
Copy-Item -Recurse -Force <download>\neurolearn\* .

git add .
git commit -m "Add API: accounts, community lesson authoring, review, progress

- FastAPI backend with JWT auth and cumulative roles
- Versioned lessons; published versions immutable
- Reviewer approval required before a lesson goes live
- Allowlist content validation; no raw HTML, no client-supplied code
- Server-side grading; answers never sent to the client
- 29 tests, ruff clean"

git push -u origin feat/accounts-and-authoring
```

Open a PR rather than pushing straight to `main`, so CI runs once before it
lands.

### Verify before you push

```bash
cd server
pip install -e ".[dev]"
pytest -q          # expect 29 passed
ruff check src tests
```

## 2. Suite

The Suite changes are additive too — three new backend files, three new
components, one CI workflow. Nothing existing is deleted.

```powershell
cd ~\Documents\NeuroTendrils\suite
git checkout -b feat/batch-and-ui

# backend
Copy-Item <download>\neurotendrils\backend\src\suite_backend\neuroflow\batch.py `
          backend\src\suite_backend\neuroflow\
Copy-Item <download>\neurotendrils\backend\src\suite_backend\ipc\handlers\batch_cmds.py `
          backend\src\suite_backend\ipc\handlers\
Copy-Item <download>\neurotendrils\backend\tests\test_phase_26_batch.py backend\tests\

# frontend
Copy-Item <download>\neurotendrils\apps\desktop\src\theme.css apps\desktop\src\
Copy-Item <download>\neurotendrils\apps\desktop\src\components\* apps\desktop\src\components\

# CI
New-Item -ItemType Directory -Force .github\workflows
Copy-Item <download>\.github\workflows\suite-ci.yml .github\workflows\
```

Then three edits you have to make by hand:

**a. Register the handler.** In `backend/src/suite_backend/ipc/handlers/__init__.py`,
next to the other imports:

```python
from suite_backend.ipc.handlers import batch_cmds  # noqa: F401
```

**b. Allowlist the commands.** In
`apps/desktop/src-tauri/permissions/suite.toml`, add `batch.preview`,
`batch.execute`, `recipe.export`, `recipe.import`. They are rejected until you
do.

**c. Import the theme.** In `apps/desktop/src/main.tsx`, add
`import "./theme.css";` above the `App.css` import, then delete the `:root` and
`[data-theme]` blocks at the top of `App.css` — they now duplicate the tokens
and will fight them.

### Add the missing LICENSE

`suite/README.md` says "Proprietary" and there is no LICENSE file. The CI job
`license-boundary` will pass either way, but the gap is worth closing now:

```powershell
Set-Content suite\LICENSE "Copyright 2026 NeuroTendrils. All rights reserved.`n`nThis software is proprietary. No permission is granted to copy, modify, or`ndistribute it without written permission from NeuroTendrils."
```

### Verify

```bash
cd backend && pytest tests/test_phase_26_batch.py -q   # expect 15 passed
cd ../apps/desktop && npx tsc --noEmit
```

## What still needs your hands

**The lineage ribbon renders from data you don't serve yet.**
`recordings.signal_window` needs an optional `artifact_id` so it can return an
earlier derivative instead of head. Until that lands, the ribbon is a shell.
It is a small change in `recording_cmds.py` — resolve the artifact, load its
FIF path instead of the stream's canonical one.

**`ProcessingPlan.revision` may not exist.** `batch.check_eligibility` uses it
to decide whether a recording was already derived by *this* revision of a plan.
There is a `getattr` fallback so nothing crashes, but without the field,
idempotence degrades to "skip anything this plan ever touched." Add an int that
bumps on every plan edit.

**Windows and Linux builds.** The CI workflow builds all three platforms, so
the first run will tell you what is actually broken. Your README currently says
builds only work on Mac; labs run Windows, and this is the fastest way to find
out why.

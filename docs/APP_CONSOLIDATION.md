# One NeuroTendrils desktop app

The React/Tauri shell now opens **Learn**, **NeuroFlow**, and **NeuroStudio** in
one window. Learn embeds the existing Flutter learner from a local web bundle,
preserving its lessons, quizzes, Artifact Detective simulation, course map,
Practice/You tabs, and progress behavior. There is no external website or separate
Flutter window in the desktop experience.

The existing Suite repository is the combined source workspace. NeuroLearn is
imported under `apps/neurolearn` with its internal layout intact, so content
compiler paths, Flutter assets, Python imports, and tests continue to resolve.
The import includes the local NeuroLearn working changes and untracked lesson
and test sources. Its original checkout is untouched. Git history is not rewritten.
The source checkout was based on NeuroLearn commit `cca8364`.
Caches, virtual environments, installed dependencies, and generated builds are excluded.

| Path | Purpose |
|---|---|
| `apps/desktop` | Unified React/Tauri shell: Learn, NeuroFlow, NeuroStudio |
| `apps/desktop/src/pages/learn` | Embedded learner startup, recovery, and layout |
| `apps/desktop/public/learn` | Generated offline Flutter web bundle; ignored by Git |
| `backend` | Local research sidecar and study workspace |
| `apps/neurolearn/app` | Flutter learner: Learn, Practice, You |
| `apps/neurolearn/studio` | React lesson authoring and review |
| `apps/neurolearn/server` | Learning accounts, published lessons, progress API |
| `apps/neurolearn/content`, `packs`, `tools` | Authored content, offline packs, compiler |
| `packages/theme` | Generated web palette from Flutter's NeuroColors |

The learner frame is created on first visit and remains mounted across module
changes, so an open lesson or quiz is retained. The research study and recording
also stay selected. Learn needs neither a research study nor a backend connection.

Study data remains in the research workspace. Learning progress is stored on the
desktop app's local origin, independently of the selected study. Existing progress
from a separately installed mobile/web learner is not automatically transferred.
The optional learning API and authoring accounts remain separate from local desktop
progress; no account sync or automatic grading handoff is introduced.

## Develop from the repository root

Install Flutter on PATH and the existing Node/Rust/Python desktop tools. Then
install package dependencies once:

```bash
npm --prefix apps/desktop ci
npm --prefix apps/neurolearn/studio ci
npm --prefix apps/neurolearn/tools/content-compiler ci
cd apps/neurolearn/app
flutter pub get
cd ../../..
```

Launch the one desktop app from the repository root:

```bash
npm run dev             # Tauri window with Learn, NeuroFlow, NeuroStudio
```

`apps/desktop` automatically runs `scripts/build_learn.mjs` before Vite dev/build.
It fingerprints learner source, web bootstrap, fonts, assets, and dependencies;
an unchanged bundle is reused. Flutter builds with `/learn/` as its base path,
local renderer resources (`--no-web-resources-cdn`), and CSP-compatible compilation.
Lessons, fonts, CanvasKit, and WASM are included in the desktop distribution.
Only startup ready/error messages cross the frame boundary. No learner data or
privileged desktop APIs are passed through that bridge.

After editing Flutter code while the desktop dev server is already running, run
`npm run build:learn` and reload the desktop window. `npm run check:learn` verifies
that the generated bundle matches its sources without requiring another build.
End users do not need the Flutter SDK or a local web server.

Optional contributor tools remain available: `npm run dev:learn` runs Flutter in
Chrome; `npm run dev:authoring` runs lesson authoring on port 5174 and proxies `/api`
to port 8000. These are development tools, not additional desktop windows.
For the optional learning API, use its own environment:

```bash
cd apps/neurolearn/server
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn neurolearn_api.main:app --reload
```

See [NeuroLearn's README](../apps/neurolearn/README.md) for the existing account
and publishing rules. The authoring proxy avoids cross-origin requests during
local development. Configure actual origins and secrets for deployments.

## Verify and release

Root commands: `check:theme`, `check:content`, `check:learn`, `test:suite`,
`test:learn`, `build`, and `build:authoring`. `sync:theme` regenerates the shared
web colors. `npm run build` builds both Learn and the desktop frontend.
For a full distributable with the frozen Python sidecar, run `npm run tauri:build`
inside `apps/desktop`. CI and all desktop release runners install Flutter before
building so the learner is included in the same bundle. Desktop keeps `v*` release
tags; optional standalone learner releases use `neurolearn-v*`. Existing publishing
still requires `RELEASES_TOKEN`.

## Source boundaries

The research README identifies Suite as proprietary; NeuroLearn's API metadata
and source headers identify AGPL-3.0-or-later. This import preserves those notices
and does not assign a new repository-wide license. Do not treat consolidation as
a relicensing decision. The source checkouts did not include the LICENSE files
referenced by their documentation; that remains unresolved for distribution.

## Verification of this import

- Desktop: build, lint, typecheck, 22 unit tests and 64 UI tests passed, including
  offline Learn access, startup failure/retry/timeout, frame identity checks, and
  preservation of the learner and active recording when switching modules.
- NeuroLearn: Flutter analysis and 28 tests passed; dependency lock preserved.
- Authoring: TypeScript and production build passed.
- Learning API: 46 tests passed, with dependency deprecation warnings.
- Content: all three lessons validated; shared palette matches the Dart source.
- UI static audit and DESIGN.md lint passed without findings/errors.
- A macOS debug `.app` was built and opened from bundled `tauri://localhost`
  assets. The connected research shell and embedded course map rendered in one
  window with native-accessible lesson controls. Full study processing continues
  to be covered by existing UI tests; hosted CI and mobile installers have not
  been run locally.

# NeuroTendrils Suite

Proprietary local-first EEG research environment.

## Modules

1. **NeuroFlow** — import, inspect/visualize EEG, manual rejection, plans, ERP, ICA
2. **NeuroStudio** — model templates (EEGNet…), local training stubs, export
3. **Hub** — future cloud sharing (interfaces only)
4. **Teams** — future paid private org sharing (interfaces only)

## Architecture

```text
React UI → Tauri allowlisted invoke → Unix socket IPC → Backend sidecar
```

Backend launch order (no hardcoded machine paths):

1. **PyInstaller sidecar** `suite-backend-<target>` (shipping / `npm run sidecar`)
2. **Repo `.venv`** via `python -m suite_backend` (dev; auto-created by `npm run setup`)
3. Optional overrides: `SUITE_BACKEND` (sidecar path) or `SUITE_PYTHON` (python path)

No localhost TCP API. Python never evaluates UI-supplied code.

## Develop

```bash
# Once (or anytime): creates .venv and installs backend
./scripts/ensure_dev.sh

# Desktop — setup runs automatically
cd apps/desktop
npm install
npm run tauri:dev
```

Use the **NeuroTendrils Suite desktop window**, not a browser tab on `localhost:5173`.

## Ship backend without requiring a system Python

```bash
./scripts/build_sidecar.sh
# writes apps/desktop/src-tauri/binaries/suite-backend-$(rustc host)

cd apps/desktop
npm run tauri:build
```

Tauri bundles `binaries/suite-backend` as `externalBin`. The app prefers that sidecar at runtime.

Workspace data lives under the OS app data directory (`…/workspace/studies/...`).

# NeuroTendrils — Suite and NeuroLearn

One desktop app with **Learn**, **NeuroFlow**, and **NeuroStudio**, using
NeuroLearn's blue and pink palette. Learn bundles the existing Flutter lesson
player, quizzes, simulation, and local progress inside the React/Tauri window.
This repo also includes mobile source, content, authoring tools, and the learning API. Start with the
[workspace guide](docs/APP_CONSOLIDATION.md) for layout, setup, and root commands.

## Modules

**Learn** — offline EEG lessons, quizzes, simulations, and local progress; no study or backend required.

**BCI Lab** — EEG → AI prediction → safety gate → Waveshare RoArm-M2-S arm, with simulated or prerecorded EEG (no live EEG yet). See [docs/guides/ROBOT_ARM.md](docs/guides/ROBOT_ARM.md).

1. **NeuroFlow** — import, visualize, reject, plans, ICA/ERP, epochs, features, analysis
2. **NeuroStudio** — datasets/splits, training-only selection of regularized EEG baselines, held-out eval/infer/explain, reports, export
3. **Hub** — future cloud sharing (interfaces only)
4. **Teams** — future paid private org sharing (interfaces only)

## Documentation

Start at [docs/README.md](docs/README.md) (architecture, phases 1–25, IPC, user/developer guides).

## Architecture

```text
React UI → Tauri allowlisted invoke → local IPC → Backend sidecar
```

Local IPC is a private Unix domain socket on macOS/Linux and a named pipe on Windows.

Backend launch order (no hardcoded machine paths):

1. **PyInstaller sidecar** `suite-backend-<target>` (shipping / `npm run sidecar`)
2. **Repo `.venv`** via `python -m suite_backend` (dev; auto-created by `npm run setup`)
3. Optional overrides: `SUITE_BACKEND` (sidecar path) or `SUITE_PYTHON` (python path)

No localhost TCP API. Python never evaluates UI-supplied code.

## Develop

Works the same on macOS, Windows, and Linux. Install Flutter on PATH as well as
Node, Rust ([rustup](https://rustup.rs)), and Python 3.11+. On Windows, also install
the Visual Studio C++ Build Tools (Tauri needs them) and tick “Add python.exe to PATH”
in the Python installer.
Desktop dev/build commands automatically build and embed Learn when its sources
change. End users need only the desktop app, with no Flutter installation.

```bash
# Desktop — setup (creates .venv and installs the backend) runs automatically
cd apps/desktop
npm install
npm run tauri:dev
```

All scripts are Node, so they run from Terminal, PowerShell, or Command Prompt alike.
`npm run setup` alone (re)creates the venv.

Use the **NeuroTendrils Suite desktop window**, not a browser tab on `localhost:5173`.
Vite only serves the UI into that window; if you only see “Local: http://localhost:5173/”, wait for the Rust build — or free a stuck port with `npm run free-port` and retry.

## Ship backend without requiring a system Python

```bash
cd apps/desktop
npm run tauri:build   # runs `npm run sidecar` first
```

`npm run sidecar` writes `apps/desktop/src-tauri/binaries/suite-backend-<rustc host>`
(`.exe` on Windows). A sidecar is built for the OS it runs on: build on Windows for a
Windows installer, on a Mac for a Mac app.

Tauri bundles `binaries/suite-backend` as `externalBin`. The app prefers that sidecar at runtime.

Workspace data lives under the OS app data directory (`…/workspace/studies/...`).

EMOTIV Insight capture, CSV import, model validation and privacy defaults: [setup guide](docs/guides/EMOTIV_INSIGHT.md).

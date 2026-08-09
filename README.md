# NeuroTendrils Suite

Proprietary local-first EEG research environment.

## Modules

1. **NeuroFlow** — import, inspect/visualize EEG, manual rejection, plans, ERP, ICA
2. **NeuroStudio** — model templates (EEGNet…), local training stubs, export
3. **Hub** — future cloud sharing (interfaces only)
4. **Teams** — future paid private org sharing (interfaces only)

## Architecture

```text
React UI → Tauri allowlisted invoke → Unix socket IPC → Python (MNE / our algorithms)
```

No localhost TCP API. Python never evaluates UI-supplied code.

## Develop

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]"
pytest backend/tests -q

# Desktop (requires Rust/cargo on PATH)
# If `cargo` is missing: curl https://sh.rustup.rs -sSf | sh
# then: source "$HOME/.cargo/env"   (or restart the terminal)
export SUITE_PYTHON="$PWD/.venv/bin/python"
cd apps/desktop
npm install
npm run tauri:dev
```

Use the **NeuroTendrils Suite desktop window**. Do not open `http://localhost:5173` in Chrome/Safari — that page has no Tauri IPC (`invoke` will fail).

`npm run tauri:dev` also prepends `$HOME/.cargo/bin` so cargo is found even if your shell profile was not updated.

Workspace data is stored under the app data directory (`workspace/studies/...`).

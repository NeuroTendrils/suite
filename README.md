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
# If `cargo` is missing: curl https://sh.rustup.rs -sSf | sh && source "$HOME/.cargo/env"
cd apps/desktop
npm install
npm run tauri:dev
```

`npm run tauri:dev` sets `SUITE_PYTHON` to the **repo-root** `.venv` (`../../.venv/bin/python` from `apps/desktop`). Do not point it at `apps/desktop/.venv`.

Use the **NeuroTendrils Suite desktop window**. Do not open `http://localhost:5173` in Chrome/Safari — that page has no Tauri IPC (`invoke` will fail).

Workspace data is stored under the app data directory (`workspace/studies/...`).

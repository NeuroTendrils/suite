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

# Desktop (requires Rust)
export SUITE_PYTHON="$PWD/.venv/bin/python"
cd apps/desktop
npm install
npm run tauri:dev
```

Workspace data is stored under the app data directory (`workspace/studies/...`).

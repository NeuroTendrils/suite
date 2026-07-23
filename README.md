# NeuroTendrils Suite

Local-only desktop suite for EEG preprocessing, model training, and learning.

## Python workers

Create the local venv the app discovers automatically:

```bash
# macOS / Linux
./python/setup_venv.sh

# Windows
powershell -File python/setup_venv.ps1
```

Override discovery with `NEUROTENDRILS_PYTHON` or `NEUROTENDRILS_VENV` if needed.
The resolved interpreter is shown in Settings → Info.

Shared JSON-lines IPC helpers: [`workers/_shared`](workers/_shared)
(`nt_ipc`, Apache-2.0). NeuroFlow is a git submodule at
`workers/neuroflow`.

```bash
git submodule update --init --recursive

PYTHONPATH=workers/_shared python -m unittest discover -s workers/_shared/tests -v
PYTHONPATH=workers/_shared:workers/neuroflow .venv/bin/python tests/test_ipc_roundtrip.py

cmake --build build --target neurotendrils_ipc_roundtrip
./build/neurotendrils_ipc_roundtrip   # run from the suite repo root
```

## License

The NeuroTendrils suite GUI is proprietary.

NeuroFlow (`workers/neuroflow` submodule) is AGPL-3.0-licensed. The IPC
helpers under `workers/_shared/` are Apache-2.0.

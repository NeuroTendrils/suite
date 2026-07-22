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

## License

The NeuroTendrils suite GUI is proprietary.

The NeuroFlow worker under `workers/neuroflow/` is AGPL-3.0-licensed;
see [`workers/neuroflow/LICENSE`](workers/neuroflow/LICENSE). The suite
GUI remains proprietary.

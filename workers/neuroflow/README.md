# NeuroFlow

EEG preprocessing worker for the NeuroTendrils suite (filter, notch, reref,
resample, ICA, event-locked epoching, suggested augmentation).

## Quick start

```bash
pip install -r requirements.txt
python -m neuroflow ping
python -m neuroflow fingerprint --path /path/to/recording.fif
python -m neuroflow catalog
python -m neuroflow run --input in.fif --output out.fif --plan plan.json
```

`neuroflow/steps.py` is the source of truth for recipe steps and param schemas.
Manual prep (montage, crop, bad spans, labels) lives in the desktop Inspector —
not in this catalog.

## License

Proprietary — part of the NeuroTendrils suite.

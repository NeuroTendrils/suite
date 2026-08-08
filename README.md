# NeuroTendrils Suite

Local desktop suite for EEG preprocessing, model training, and collaboration.

## Run

```bash
cd /path/to/suite
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r workers/neurostudio/requirements.txt   # torch for training
python -m neurotendrils
```

Flow: **Recording → Inspect** (scroll / paint BAD / montage / labels) → Fingerprint → Plan → Run → **Review** (ICA / ERP / augment) → NeuroStudio train.

Supported imports include EDF/BDF/FIF/SET/BrainVision/CNT/GDF and numeric **.txt** (converted to FIF on import).

## License

The NeuroTendrils suite (GUI, NeuroFlow, and NeuroStudio) is proprietary.

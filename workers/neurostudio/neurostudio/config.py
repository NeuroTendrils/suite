"""Configuration for local NeuroStudio preprocess-and-train runs.

Every knob the pipeline uses lives here as a plain variable. Edit a value,
then run:

    python -m neurostudio.preprocessing

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from pathlib import Path

# --- Data -------------------------------------------------------------------
# Which epoched FIF to train on (BCI IV-2a subject 1 by default).
DATA_PATH = Path.home() / "Documents" / "neurostudio_data" / "bci_iv2a_subj1-epo.fif"

# --- Preprocessing ----------------------------------------------------------
# Per-channel z-score. Stats are fit on the TRAIN split only, then applied to
# the test split — the biggest win for stable EEG training, with no leakage.
STANDARDIZE = True
# Clip standardized values to +/- this many sigma to tame artifact spikes.
# Set to 0 to turn clipping off.
CLIP_SIGMA = 6.0

# --- Model ------------------------------------------------------------------
TEMPLATE_ID = "eegnet_mi_v1"   # eegnet_mi_v1 | shallow_mi_v1 | eegnet_erp_v1
DROPOUT = 0.25
F1 = 8                         # temporal filters
DEPTH = 2                      # depth multiplier (D)
KERNEL_LENGTH = 64             # temporal kernel length

# --- Optimization -----------------------------------------------------------
DEVICE = "cuda"                 # cpu | cuda | mps | auto
EPOCHS = 60
BATCH_SIZE = 64
LR = 1e-3                      # learning rate
WEIGHT_DECAY = 5e-4            # L2 regularization (helps single-subject MI)
OPTIMIZER = "adamw"           # adam | adamw | sgd

# --- Split & early stopping -------------------------------------------------
SEED = 42
VAL_SPLIT = 0.2                # fraction of trials held out for the test set
EARLY_STOP_PATIENCE = 15       # stop if test acc stalls this many epochs (0 = off)

# --- Output -----------------------------------------------------------------
# Where the trained model is saved after `run.py`, and loaded from by `predict.py`.
MODEL_OUT = Path.home() / "Documents" / "neurostudio_data" / "trained_eegnet.pt"

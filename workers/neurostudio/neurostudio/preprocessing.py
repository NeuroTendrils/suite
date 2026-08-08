"""Preprocess EEG trials and train the NeuroStudio model end-to-end.

This is the runnable, transparent counterpart to `train.py`: it reuses the
*same* data loader and the *same* model (`train._build_model`), adds a proper
signal-preprocessing stage (leak-free per-channel standardization + outlier
clipping), then trains while printing a per-epoch report with a train/test
gap and an automatic under/over-fitting diagnosis.

Run it with the settings in `config.py`:

    python -m neurostudio.preprocessing

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from . import config
from .devices import resolve_device
from .templates import find_template
from .train import (
    TrainError,
    _build_model,
    _confusion_matrix,
    _evaluate,
    _prepare_arrays,
    _seed_everything,
    _stratified_split,
)

# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------


def load_trials(path: str | Path, *, seed: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Load an epoched FIF into (X, y, meta).

    Reuses train._prepare_arrays so labelling/epoching logic stays in one
    place. X has shape (N, 1, C, T); the singleton dim is the model's input
    convention. Raises if the file yields no real labels.
    """
    x, y, data_mode, meta = _prepare_arrays(Path(path), seed=seed)
    if data_mode == "synthetic_demo":
        raise TrainError(
            "no_labels",
            f"{path} has no usable trial labels; preprocessing needs real "
            "epoched/annotated EEG (see the MOABB pull).",
        )
    meta["data_mode"] = data_mode
    return x, y, meta


def fit_channel_stats(x_train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-channel mean/std over the TRAIN trials only (no val leakage).

    x_train: (N, 1, C, T) -> stats broadcastable as (1, 1, C, 1).
    """
    mean = x_train.mean(axis=(0, 1, 3), keepdims=True)
    std = x_train.std(axis=(0, 1, 3), keepdims=True)
    std = np.where(std < 1e-7, 1.0, std)  # guard flat/dead channels
    return mean.astype(np.float32), std.astype(np.float32)


def apply_standardization(
    x: np.ndarray, mean: np.ndarray, std: np.ndarray, *, clip_sigma: float
) -> np.ndarray:
    """z-score with the given stats, then optionally clip outliers."""
    z = (x - mean) / std
    if clip_sigma and clip_sigma > 0:
        z = np.clip(z, -clip_sigma, clip_sigma)
    return z.astype(np.float32)


def standardize_like_training(
    x: np.ndarray, mean: np.ndarray | None, std: np.ndarray | None, clip_sigma: float
) -> np.ndarray:
    """Apply saved training stats to new trials (no stats -> passthrough)."""
    if mean is None or std is None:
        return x.astype(np.float32)
    return apply_standardization(x, mean, std, clip_sigma=clip_sigma)


def preprocess(x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    """Split, standardize (fit on train), and return arrays ready for torch."""
    train_idx, val_idx = _stratified_split(
        y, seed=config.SEED, train_frac=1.0 - config.VAL_SPLIT
    )
    x_train, x_val = x[train_idx], x[val_idx]
    y_train, y_val = y[train_idx], y[val_idx]

    chan_mean = chan_std = None
    if config.STANDARDIZE:
        chan_mean, chan_std = fit_channel_stats(x_train)
        x_train = apply_standardization(x_train, chan_mean, chan_std, clip_sigma=config.CLIP_SIGMA)
        x_val = apply_standardization(x_val, chan_mean, chan_std, clip_sigma=config.CLIP_SIGMA)

    return {
        "x_train": x_train,
        "y_train": y_train,
        "x_val": x_val,
        "y_val": y_val,
        "n_channels": int(x.shape[2]),
        "n_times": int(x.shape[3]),
        "n_classes": int(len(np.unique(y))),
        # Kept so new/unseen trials can be standardized the same way at predict time.
        "chan_mean": chan_mean,
        "chan_std": chan_std,
    }


# ---------------------------------------------------------------------------
# Training + reporting
# ---------------------------------------------------------------------------


def _make_optimizer(model):
    import torch

    name = config.OPTIMIZER.lower()
    kw = dict(lr=config.LR, weight_decay=config.WEIGHT_DECAY)
    if name == "adamw":
        return torch.optim.AdamW(model.parameters(), **kw)
    if name == "sgd":
        return torch.optim.SGD(model.parameters(), momentum=0.9, **kw)
    return torch.optim.Adam(model.parameters(), **kw)


def _model_config() -> dict[str, Any]:
    """Map the flat config knobs onto the keys train._build_model expects."""
    return {
        "drop_prob": config.DROPOUT,
        "F1": config.F1,
        "D": config.DEPTH,
        "kernel_length": config.KERNEL_LENGTH,
    }


def train_and_report(data: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Train the actual model, printing a per-epoch report as we go."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    device_name = resolve_device(config.DEVICE)
    torch_device = torch.device(device_name)
    _seed_everything(config.SEED)

    template = find_template(config.TEMPLATE_ID) or {"model_family": "eegnet"}
    n_channels, n_times, n_classes = (
        data["n_channels"], data["n_times"], data["n_classes"]
    )
    chance = 1.0 / n_classes

    x_train = torch.tensor(data["x_train"], dtype=torch.float32)
    y_train = torch.tensor(data["y_train"], dtype=torch.long)
    x_val = torch.tensor(data["x_val"], dtype=torch.float32)
    y_val = torch.tensor(data["y_val"], dtype=torch.long)

    bs = config.BATCH_SIZE
    train_loader = DataLoader(
        TensorDataset(x_train, y_train), batch_size=min(bs, len(y_train)), shuffle=True
    )
    val_loader = DataLoader(
        TensorDataset(x_val, y_val), batch_size=min(bs, len(y_val)), shuffle=False
    )

    model = _build_model(
        template=template,
        n_channels=n_channels,
        n_times=n_times,
        n_classes=n_classes,
        config=_model_config(),
    ).to(torch_device)

    optimizer = _make_optimizer(model)
    criterion = nn.CrossEntropyLoss()

    n_params = sum(p.numel() for p in model.parameters())
    _print_header(meta, data, device_name, n_params, chance)

    history: list[dict[str, Any]] = []
    best_acc, best_epoch, best_state, stale = -1.0, 0, None, 0

    print(f"{'Epoch':>5}  {'TrLoss':>7}  {'TrAcc':>6}  {'TeAcc':>6}  {'Gap':>6}   Note")
    print("-" * 58)

    for epoch in range(1, config.EPOCHS + 1):
        model.train()
        loss_sum, correct, total = 0.0, 0, 0
        for xb, yb in train_loader:
            xb, yb = xb.to(torch_device), yb.to(torch_device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(xb)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.item()) * len(yb)
            correct += int((logits.argmax(1) == yb).sum().item())
            total += len(yb)

        train_loss = loss_sum / max(1, total)
        train_acc = correct / max(1, total)
        _, val_acc, _ = _evaluate(model, val_loader, criterion, torch_device)
        gap = train_acc - val_acc

        note = ""
        if val_acc > best_acc:
            best_acc, best_epoch, stale = val_acc, epoch, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            note = "<- best"
        else:
            stale += 1
            if gap > 0.25 and train_acc > 0.85:
                note = "overfit gap"

        history.append(
            {"epoch": epoch, "train_loss": train_loss, "train_acc": train_acc,
             "val_acc": val_acc, "gap": gap}
        )
        print(f"{epoch:>5}  {train_loss:>7.4f}  {train_acc:>6.3f}  "
              f"{val_acc:>6.3f}  {gap:>+6.3f}   {note}")

        if config.EARLY_STOP_PATIENCE and stale >= config.EARLY_STOP_PATIENCE:
            print(f"  early stop: no val improvement for "
                  f"{config.EARLY_STOP_PATIENCE} epochs")
            break

    # Restore best weights for the final report.
    if best_state is not None:
        model.load_state_dict(best_state)
    _, final_acc, preds = _evaluate(model, val_loader, criterion, torch_device, return_preds=True)
    y_true, y_pred = preds
    confusion = _confusion_matrix(y_true, y_pred, n_classes)

    _print_summary(history, confusion, meta, chance, best_epoch, best_acc, final_acc)

    # Show a few real predictions, then save the trained model for reuse.
    class_names = meta.get("class_names", [])
    _print_prediction_demo(model, data["x_val"], data["y_val"], class_names, device_name)
    save_path = save_model(model, data, meta)
    print(f"saved model -> {save_path}   (reuse it with:  python predict.py)")
    print("=" * 58)

    return {
        "history": history,
        "best_acc": best_acc,
        "best_epoch": best_epoch,
        "final_acc": final_acc,
        "confusion": confusion,
        "diagnosis": _diagnose(history, chance),
        "model": model,
        "saved_to": save_path,
    }


# ---------------------------------------------------------------------------
# Diagnosis + printing
# ---------------------------------------------------------------------------


def _diagnose(history: list[dict[str, Any]], chance: float) -> str:
    """Heuristic under/over/good-fit verdict from the training curve."""
    if not history:
        return "no epochs ran"
    final = history[-1]
    tr, te = final["train_acc"], final["val_acc"]
    gap = tr - te
    best_te = max(h["val_acc"] for h in history)
    best_ep = max(range(len(history)), key=lambda i: history[i]["val_acc"]) + 1
    peaked_early = best_ep < len(history) * 0.6 and (best_te - te) > 0.05

    if tr < chance + 0.15:
        return ("UNDERFITTING - train accuracy is barely above chance. The model "
                "isn't learning: try more epochs, a higher learning rate, or more capacity.")
    if gap > 0.25 and tr > 0.80:
        return ("OVERFITTING - train accuracy far exceeds test. Memorizing the "
                "training trials: add dropout/weight_decay, get more data, or train fewer epochs.")
    if peaked_early:
        return (f"OVERFITTING (late) - test accuracy peaked at epoch {best_ep} then "
                "declined. Early stopping (restoring best weights) is the fix; it's already applied.")
    if gap > 0.12:
        return ("MILD OVERFITTING - a modest train/test gap. Usable, but light "
                "regularization or a touch more data would tighten it.")
    return "GOOD FIT - train and test accuracy track closely; the model generalizes."


def _print_header(meta, data, device_name, n_params, chance) -> None:
    print("=" * 58)
    print("NeuroStudio - preprocess & train")
    print("=" * 58)
    print(f"data       : {config.DATA_PATH}")
    print(f"trials     : {len(data['y_train'])} train / {len(data['y_val'])} test  "
          f"(val_split={config.VAL_SPLIT})")
    print(f"signal     : {data['n_channels']} ch x {data['n_times']} samples @ "
          f"{meta.get('sfreq', '?')} Hz")
    print(f"classes    : {data['n_classes']}  {meta.get('class_names', [])}  "
          f"(chance {chance:.3f})")
    print(f"preprocess : standardize={config.STANDARDIZE} clip_sigma={config.CLIP_SIGMA}")
    print(f"model      : {config.TEMPLATE_ID}  ({n_params:,} params)")
    print(f"optim      : {config.OPTIMIZER} lr={config.LR} wd={config.WEIGHT_DECAY} "
          f"dropout={config.DROPOUT} bs={config.BATCH_SIZE} epochs={config.EPOCHS}")
    print(f"device     : {device_name}")
    print("-" * 58)


def _print_summary(history, confusion, meta, chance, best_epoch, best_acc, final_acc) -> None:
    final = history[-1]
    print("-" * 58)
    print("RESULTS")
    print(f"  epochs run     : {len(history)}")
    print(f"  final train acc: {final['train_acc']:.3f}")
    print(f"  final test acc : {final['val_acc']:.3f}")
    print(f"  best test acc  : {best_acc:.3f} (epoch {best_epoch})  <- weights restored")
    print(f"  vs chance      : {best_acc - chance:+.3f}")
    print(f"  train/test gap : {final['train_acc'] - final['val_acc']:+.3f}")
    names = meta.get("class_names") or [str(i) for i in range(len(confusion))]
    print("  confusion (rows=true, cols=pred):")
    print("      " + "  ".join(f"{n[:6]:>6}" for n in names))
    for name, row in zip(names, confusion):
        print(f"    {name[:6]:>6} " + "  ".join(f"{v:>6}" for v in row))
    print(f"  diagnosis      : {_diagnose(history, chance)}")
    print("=" * 58)


# ---------------------------------------------------------------------------
# Inference — feed trials in, get predictions out
# ---------------------------------------------------------------------------


def predict(model, x: np.ndarray, class_names: list[str], device: str = "cpu") -> list[dict[str, Any]]:
    """Run the model on already-standardized trials (N, 1, C, T).

    Returns one dict per trial: {label, confidence, probs}.
    """
    import torch

    model.eval()
    xt = torch.tensor(np.asarray(x, dtype=np.float32)).to(device)
    with torch.no_grad():
        probs = torch.softmax(model(xt), dim=1).cpu().numpy()

    def name(i: int) -> str:
        return class_names[i] if i < len(class_names) else str(i)

    out = []
    for row in probs:
        top = int(row.argmax())
        out.append(
            {
                "label": name(top),
                "confidence": float(row[top]),
                "probs": {name(j): float(row[j]) for j in range(len(row))},
            }
        )
    return out


def save_model(model, data: dict[str, Any], meta: dict[str, Any], path: str | Path | None = None) -> Path:
    """Persist weights + everything needed to preprocess and rebuild later."""
    import torch

    out = Path(path or config.MODEL_OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "template_id": config.TEMPLATE_ID,
            "model_config": _model_config(),
            "n_channels": data["n_channels"],
            "n_times": data["n_times"],
            "n_classes": data["n_classes"],
            "class_names": meta.get("class_names", []),
            "chan_mean": data.get("chan_mean"),
            "chan_std": data.get("chan_std"),
            "clip_sigma": config.CLIP_SIGMA,
        },
        out,
    )
    return out


def load_model(path: str | Path | None = None):
    """Rebuild a saved model. Returns (model, blob) where blob has the stats."""
    import torch

    src = Path(path or config.MODEL_OUT)
    if not src.is_file():
        raise TrainError(
            "file_not_found",
            f"no saved model at {src}; run `python run.py` first to train one.",
        )
    blob = torch.load(src, map_location="cpu", weights_only=False)
    template = find_template(blob["template_id"]) or {"model_family": "eegnet"}
    model = _build_model(
        template=template,
        n_channels=blob["n_channels"],
        n_times=blob["n_times"],
        n_classes=blob["n_classes"],
        config=blob["model_config"],
    )
    model.load_state_dict(blob["model_state"])
    model.eval()
    return model, blob


def _print_prediction_demo(model, x_val, y_val, class_names, device, n: int = 6) -> None:
    n = min(n, len(x_val))
    preds = predict(model, x_val[:n], class_names, device)
    print("-" * 58)
    print(f"SAMPLE PREDICTIONS ({n} held-out test trials)")
    print(f"  {'#':>2}  {'actual':>10}  {'predicted':>10}  {'conf':>5}  hit")
    for k, p in enumerate(preds):
        yi = int(y_val[k])
        actual = class_names[yi] if yi < len(class_names) else str(yi)
        hit = "ok" if p["label"] == actual else "  "
        print(f"  {k:>2}  {actual:>10}  {p['label']:>10}  {p['confidence']:>5.2f}  {hit}")


def run_prediction(
    data_path: str | Path | None = None,
    model_path: str | Path | None = None,
    n_show: int = 12,
) -> list[dict[str, Any]]:
    """Load a saved model + a FIF, standardize like training, print predictions."""
    model, blob = load_model(model_path)
    class_names = blob.get("class_names", [])

    x, y, meta = load_trials(data_path or config.DATA_PATH, seed=config.SEED)
    x = standardize_like_training(
        x, blob.get("chan_mean"), blob.get("chan_std"), blob.get("clip_sigma", 0.0)
    )
    preds = predict(model, x, class_names, device="cpu")

    def actual(k: int) -> str:
        yi = int(y[k])
        return class_names[yi] if yi < len(class_names) else str(yi)

    correct = sum(1 for k, p in enumerate(preds) if p["label"] == actual(k))

    print("=" * 58)
    print("NeuroStudio - inference (load saved model -> predict)")
    print("=" * 58)
    print(f"model : {Path(model_path or config.MODEL_OUT)}")
    print(f"data  : {Path(data_path or config.DATA_PATH)}")
    print(f"trials: {len(preds)}  |  classes: {class_names}")
    print("-" * 58)
    print(f"  {'#':>3}  {'actual':>10}  {'predicted':>10}  {'conf':>5}  hit")
    for k in range(min(n_show, len(preds))):
        p = preds[k]
        hit = "ok" if p["label"] == actual(k) else "  "
        print(f"  {k:>3}  {actual(k):>10}  {p['label']:>10}  {p['confidence']:>5.2f}  {hit}")
    print("-" * 58)
    print(f"predicted {correct}/{len(preds)} correct across ALL loaded trials")
    print("  (note: includes trials used in training - illustrative, not a test score)")
    print("=" * 58)
    return preds


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> dict[str, Any]:
    """Load -> preprocess -> train -> report. Returns the results dict."""
    if not Path(config.DATA_PATH).is_file():
        raise TrainError(
            "file_not_found",
            f"dataset not found: {config.DATA_PATH}\n"
            "Pull it first (BCI IV-2a via MOABB) or edit config.DATA_PATH.",
        )
    x, y, meta = load_trials(config.DATA_PATH, seed=config.SEED)
    data = preprocess(x, y)
    return train_and_report(data, meta)


def main() -> int:
    try:
        run()
    except TrainError as exc:
        print(f"[{exc.code}] {exc.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

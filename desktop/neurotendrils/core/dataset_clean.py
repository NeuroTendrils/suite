"""Run a NeuroFlow plan across every member of a dataset manifest."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from neurotendrils.core.dataset_manifest import (
    DatasetManifest,
    DatasetMember,
    LabelConfig,
    SplitConfig,
    load_manifest,
    new_dataset_dir,
    resolve_member_path,
    save_manifest,
)
from neurotendrils.core.naming import sanitize_base_name

ProgressCb = Callable[[dict[str, Any]], None]


class DatasetCleanError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _member_as_raw_path(path: Path, scratch: Path) -> tuple[Path, dict[str, Any] | None]:
    """Return a Raw path for Flow. Epoched members are concatenated to temp Raw."""
    import mne
    import numpy as np

    try:
        mne.io.read_raw(str(path), preload=False, verbose="ERROR")
        return path, None
    except Exception:  # noqa: BLE001
        pass

    epochs = mne.read_epochs(str(path), preload=True, verbose="ERROR")
    data = epochs.get_data(copy=True)  # (n, c, t)
    n, c, t = data.shape
    continuous = data.transpose(1, 0, 2).reshape(c, n * t)
    info = mne.create_info(epochs.ch_names, float(epochs.info["sfreq"]), ch_types="eeg")
    raw = mne.io.RawArray(continuous.astype(np.float64), info, verbose="ERROR")
    # Rebuild class annotations from epoch events.
    event_id = dict(epochs.event_id or {})
    code_to_name = {int(v): str(k) for k, v in event_id.items()}
    onsets = []
    durs = []
    descs = []
    for i, code in enumerate(np.asarray(epochs.events[:, 2], dtype=int)):
        onsets.append(i * t / float(epochs.info["sfreq"]))
        durs.append(t / float(epochs.info["sfreq"]))
        descs.append(code_to_name.get(int(code), f"class_{int(code)}"))
    if onsets:
        raw.set_annotations(mne.Annotations(onsets, durs, descs))
    tmp = scratch / f"{path.stem}_as_raw.fif"
    raw.save(str(tmp), overwrite=True, verbose="ERROR")
    return tmp, {
        "from_epochs": True,
        "n_epochs": n,
        "epoch_samples": t,
        "event_id": event_id,
    }


def clean_dataset_with_plan(
    manifest_path: str | Path,
    plan: dict[str, Any],
    *,
    project_root: str | None = None,
    name: str | None = None,
    on_progress: ProgressCb | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Apply *plan* to each dataset member; write a new cleaned dataset.

    Returns paths + summary for the new manifest.
    """
    from neuroflow.run import RunError, run_plan

    src = load_manifest(manifest_path)
    if not src.members:
        raise DatasetCleanError("invalid_dataset", "Dataset has no members to clean")

    base = name or f"{sanitize_base_name(src.name, 'dataset')}_clean"
    out_dir = new_dataset_dir(base, project_root=project_root).resolve()
    members_dir = out_dir / "members"
    members_dir.mkdir(parents=True, exist_ok=True)
    scratch = out_dir / ".scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    cleaned = DatasetManifest(
        version=1,
        name=out_dir.name,
        created_at=datetime.now(timezone.utc).isoformat(),
        members=[],
        label=LabelConfig(
            source=src.label.source,
            map=dict(src.label.map),
            class_names=list(src.label.class_names),
        ),
        split=SplitConfig(
            mode=src.split.mode,
            val_fraction=src.split.val_fraction,
            seed=src.split.seed,
        ),
        meta={
            **{k: v for k, v in src.meta.items() if not str(k).startswith("_")},
            "source_dataset": str(Path(manifest_path).resolve()),
            "source_name": src.name,
            "cleaned_with_plan": True,
        },
    )

    plan_snapshot = deepcopy(plan)
    total = len(src.members)
    member_results: list[dict[str, Any]] = []
    warnings: list[str] = list(cleaned.meta.get("warnings") or [])

    for index, member in enumerate(src.members):
        if should_cancel and should_cancel():
            raise DatasetCleanError("cancelled", "Dataset clean cancelled")
        try:
            in_path = resolve_member_path(src, member)
        except OSError as exc:
            warnings.append(f"Skip missing member {member.id}: {exc}")
            continue

        if on_progress:
            on_progress(
                {
                    "stage": "member",
                    "message": f"Cleaning {member.id} ({index + 1}/{total})…",
                    "current": index + 1,
                    "total": total,
                    "member": member.id,
                }
            )

        raw_in, _epoch_meta = _member_as_raw_path(in_path, scratch)
        out_path = members_dir / f"{sanitize_base_name(member.id, f'm{index}')}_raw.fif"

        try:
            # ICA often emits sklearn ConvergenceWarning on short/noisy trials —
            # keep the run going; surface only hard failures.
            import warnings

            try:
                from sklearn.exceptions import ConvergenceWarning
            except Exception:  # noqa: BLE001
                ConvergenceWarning = UserWarning  # type: ignore[misc, assignment]

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=ConvergenceWarning)
                result = run_plan(
                    raw_in,
                    out_path,
                    plan_snapshot,
                    on_progress=None,
                    should_cancel=should_cancel,
                )
        except RunError as exc:
            raise DatasetCleanError(
                exc.code, f"{member.id}: {exc.message}"
            ) from exc

        written = Path(str(result.get("output_path") or out_path)).resolve()
        if not written.is_file():
            raise DatasetCleanError(
                "output_missing", f"{member.id}: plan produced no output file"
            )

        final = (members_dir / f"{sanitize_base_name(member.id, 'm')}_raw.fif").resolve()
        if written != final:
            written.replace(final)
            written = final

        rel = written.relative_to(out_dir).as_posix()
        cleaned.members.append(
            DatasetMember(
                id=member.id,
                path=rel,
                group=member.group or member.id,
                role=member.role,
                source_path=member.source_path or str(in_path),
                class_hint=member.class_hint,
            )
        )
        member_results.append(
            {
                "id": member.id,
                "input": str(in_path),
                "output": str(written),
                "output_kind": result.get("output_kind"),
                "sfreq": result.get("sfreq"),
            }
        )

    if not cleaned.members:
        raise DatasetCleanError("no_output", "No members were cleaned successfully")

    cleaned.meta["warnings"] = warnings
    cleaned.meta["n_cleaned"] = len(cleaned.members)
    manifest_file = save_manifest(cleaned, out_dir)

    if on_progress:
        on_progress(
            {
                "stage": "done",
                "message": f"Cleaned dataset ready · {len(cleaned.members)} members",
                "manifest_path": str(manifest_file),
            }
        )

    # Drop scratch temps
    try:
        import shutil

        shutil.rmtree(scratch, ignore_errors=True)
    except OSError:
        pass

    return {
        "manifest_path": str(manifest_file.resolve()),
        "dataset_dir": str(out_dir.resolve()),
        "name": cleaned.name,
        "n_members": len(cleaned.members),
        "n_steps": len(plan_snapshot.get("steps") or []),
        "members": member_results,
        "warnings": warnings,
        "output_path": str(manifest_file.resolve()),
        "output_kind": "dataset_manifest",
        "sfreq": member_results[-1].get("sfreq") if member_results else None,
    }

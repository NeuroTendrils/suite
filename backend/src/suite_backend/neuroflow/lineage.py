"""Provenance chain resolution.

Copyright 2026 NeuroTendrils
Proprietary — see LICENSE.

The desktop lineage ribbon needs two things the backend did not previously
expose:

1. **The chain itself** — the ordered list of operations that produced the
   current state of a recording, with the parameters for each.
2. **The signal as it was at any step** — so clicking an earlier step shows
   what the data actually looked like then, rather than a label claiming it.

Both come from ``DatasetArtifact`` rows that ``execute_plan`` already writes.
Nothing new is stored; this module only reads what provenance already records.

Ordering note: artifacts form a parent chain via ``parent_id``. Sorting by
``created_at`` alone is wrong — two artifacts written in the same second would
sort arbitrarily. This walks the parent links and falls back to timestamp only
for roots.
"""

from __future__ import annotations

from typing import Any

from suite_backend.domain.models import DatasetArtifact, DataStream, Recording

# Operations that record a human judgment rather than an automated transform.
# The UI colours these differently, because "someone decided this" and "a
# filter ran" are different kinds of claim about the data.
HUMAN_OPERATIONS = {
    "mark_bad_channels",
    "interpolate_bads",
    "reject_segments",
    "ica_exclude",
    "epoch_reject",
    "unreject",
}

# Human-readable labels. Unknown operations fall back to their raw name rather
# than being hidden — an unlabelled step in the chain is still a real step.
OPERATION_LABELS = {
    "import": "Import",
    "normalize": "Normalize",
    "filter": "Filter",
    "highpass": "High-pass",
    "lowpass": "Low-pass",
    "bandpass": "Bandpass",
    "notch": "Notch",
    "resample": "Resample",
    "rereference": "Re-reference",
    "average_reference": "Re-reference",
    "apply_montage": "Montage",
    "mark_bad_channels": "Flag channels",
    "interpolate_bads": "Interpolate",
    "reject_segments": "Reject spans",
    "ica_exclude": "ICA",
    "epochs": "Epoch",
    "epoch_reject": "Reject epochs",
}


def describe_parameters(operation: str, parameters: dict[str, Any]) -> str:
    """One short string summarizing what a step did.

    Kept deliberately terse — this renders under a 74px-wide ribbon knob.
    """
    p = parameters or {}

    if operation in ("highpass", "lowpass", "notch"):
        freq = p.get("freq") or p.get("l_freq") or p.get("h_freq")
        return f"{freq} Hz" if freq is not None else ""
    if operation in ("filter", "bandpass"):
        lo, hi = p.get("l_freq"), p.get("h_freq")
        if lo is not None and hi is not None:
            return f"{lo}–{hi} Hz"
        return f"{lo or hi} Hz" if (lo or hi) is not None else ""
    if operation == "resample":
        return f"{p.get('sfreq')} Hz" if p.get("sfreq") else ""
    if operation in ("rereference", "average_reference"):
        return str(p.get("reference", "average"))
    if operation == "mark_bad_channels":
        channels = p.get("channels") or []
        return f"{len(channels)} flagged" if channels else ""
    if operation == "ica_exclude":
        excluded = p.get("exclude") or []
        return f"−{len(excluded)} comp" if excluded else ""
    if operation == "reject_segments":
        segments = p.get("segments") or []
        return f"{len(segments)} spans" if segments else ""
    if operation == "epochs":
        n = p.get("n_epochs") or p.get("count")
        return f"{n} trials" if n else ""
    if operation == "apply_montage":
        return str(p.get("montage", ""))
    return ""


def order_chain(artifacts: list[DatasetArtifact]) -> list[DatasetArtifact]:
    """Order artifacts by their parent links, oldest first.

    Artifacts whose parent is missing (or absent) are treated as roots and
    ordered by creation time among themselves.
    """
    by_id = {a.id: a for a in artifacts}
    children: dict[str | None, list[DatasetArtifact]] = {}
    for artifact in artifacts:
        parent = artifact.parent_id if artifact.parent_id in by_id else None
        children.setdefault(parent, []).append(artifact)

    for siblings in children.values():
        siblings.sort(key=lambda a: (a.created_at, a.id))

    ordered: list[DatasetArtifact] = []
    seen: set[str] = set()

    def walk(parent: str | None) -> None:
        for artifact in children.get(parent, []):
            # Defensive: a corrupt parent cycle must not hang the UI.
            if artifact.id in seen:
                continue
            seen.add(artifact.id)
            ordered.append(artifact)
            walk(artifact.id)

    walk(None)
    # Anything unreachable (cycle, or parent pointing outside this recording)
    # is appended rather than dropped. A step we cannot place is still a step.
    for artifact in artifacts:
        if artifact.id not in seen:
            ordered.append(artifact)
    return ordered


def build_chain(
    recording: Recording, artifacts: list[DatasetArtifact]
) -> list[dict[str, Any]]:
    """Return the ribbon payload for one recording."""
    mine = [a for a in artifacts if a.recording_id == recording.id]
    steps: list[dict[str, Any]] = []

    for artifact in order_chain(mine):
        operation = artifact.operation or "unknown"
        steps.append(
            {
                "id": artifact.id,
                "artifact_id": artifact.id,
                "operation": operation,
                "label": OPERATION_LABELS.get(operation, operation),
                "detail": describe_parameters(operation, artifact.parameters),
                "kind": "human" if operation in HUMAN_OPERATIONS else "filter",
                "parameters": artifact.parameters,
                "parent_id": artifact.parent_id,
                "checksum": artifact.checksum,
                "at": artifact.created_at.isoformat() if artifact.created_at else None,
                "replayable": bool(_fif_path(artifact)),
            }
        )
    return steps


def _fif_path(artifact: DatasetArtifact) -> str | None:
    """The loadable signal for an artifact, if it wrote one.

    Not every step produces a new FIF — a step that only records a decision
    has nothing to replay, and says so via ``replayable: false`` rather than
    silently showing the wrong signal.
    """
    paths = artifact.paths or {}
    for key in ("fif", "raw", "output", "path"):
        value = paths.get(key)
        if value and str(value).endswith((".fif", ".fif.gz")):
            return str(value)
    return None


def stream_at_artifact(
    recording: Recording,
    streams: list[DataStream],
    artifact: DatasetArtifact,
) -> DataStream:
    """A DataStream pointing at the signal as of ``artifact``.

    The returned stream is a detached copy — it is never persisted, so viewing
    history cannot mutate the study. This is the same guarantee the read-only
    state in the UI is promising the researcher.
    """
    path = _fif_path(artifact)
    if path is None:
        raise ValueError(
            f"step {artifact.operation!r} did not write a signal artifact — "
            "there is nothing to replay at this point"
        )

    base = next((s for s in streams if s.modality == "eeg"), None) or (
        streams[0] if streams else None
    )
    if base is None:
        raise KeyError(f"no stream attached to recording {recording.id}")

    replay = base.model_copy(deep=True)
    replay.sample_paths = {**(base.sample_paths or {}), "fif": path}
    replay.provenance = {
        **(base.provenance or {}),
        "replay_of": artifact.id,
        "read_only": True,
    }
    return replay

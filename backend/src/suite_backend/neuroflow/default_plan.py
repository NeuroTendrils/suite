"""Default NeuroFlow plan aligned with EEGLAB tutorial preprocessing (placeholder)."""

from __future__ import annotations

from suite_backend.domain.models import ProcessingPlan, ProcessingStep


def default_preprocessing_plan(*, name: str = "eeglab_tutorial_aligned") -> ProcessingPlan:
    """
    Fixed plan mirroring the common EEGLAB single-subject tutorial path
    (filter → notch → reref). Interactive steps stay in the Visualizer:
    bad channel/segment reject, ICA, epoch reject.

    Not data-adaptive — same steps every time until a real recommender exists.
    """
    return ProcessingPlan(
        name=name,
        notes=(
            "EEGLAB-tutorial-aligned placeholder (Tools → Filter / Re-reference). "
            "After execute: Visualizer → mark bad channels/segments → ICA → Epochs. "
            "Does NOT auto-run CleanRawdata/ASR or remove ICA components."
        ),
        steps=[
            # EEGLAB: Tools → Filter (high-pass ~1 Hz; we also low-pass for practicality)
            ProcessingStep(
                operation="filter_bandpass",
                parameters={"l_freq": 1.0, "h_freq": 40.0},
                output_type="recording_artifact",
            ),
            # Line noise (EEGLAB often uses CleanLine / notch plugins)
            ProcessingStep(
                operation="filter_notch",
                parameters={"freqs": [60.0]},
                output_type="recording_artifact",
            ),
            # EEGLAB: Tools → Re-reference
            ProcessingStep(
                operation="rereference",
                parameters={"ref": "average"},
                output_type="recording_artifact",
            ),
        ],
    )


def eeglab_tutorial_checklist() -> list[dict[str, str]]:
    """Human-facing mapping: EEGLAB tutorial step → Suite capability."""
    return [
        {
            "eeglab": "Import continuous data (.set / EDF / …)",
            "suite": "Import tab → import.recording",
            "status": "ok",
        },
        {
            "eeglab": "Channel locations",
            "suite": "Visualizer → Montage 10–20 / channels.apply_montage",
            "status": "ok",
        },
        {
            "eeglab": "Filter (e.g. 1 Hz HP)",
            "suite": "Preprocess → default plan filter_bandpass 1–40",
            "status": "ok",
        },
        {
            "eeglab": "Re-reference",
            "suite": "Preprocess → default plan rereference average",
            "status": "ok",
        },
        {
            "eeglab": "Reject continuous data by eye (drag + REJECT)",
            "suite": "Visualizer → drag mark + REJECT button (masks, raw untouched)",
            "status": "ok",
        },
        {
            "eeglab": "Reject bad channels",
            "suite": "Visualizer → click channel label (toggle bad)",
            "status": "ok",
        },
        {
            "eeglab": "Clean Rawdata / ASR",
            "suite": "Not implemented (placeholder detector only)",
            "status": "gap",
        },
        {
            "eeglab": "Run ICA (runica/fastica)",
            "suite": "Visualizer → ICA (MNE FastICA via scikit-learn)",
            "status": "ok",
        },
        {
            "eeglab": "Reject ICA components",
            "suite": "Visualizer → ICA → click IC to reject",
            "status": "ok",
        },
        {
            "eeglab": "Remove components (apply)",
            "suite": "Decision stored; apply-to-new-artifact not wired yet",
            "status": "partial",
        },
        {
            "eeglab": "Extract epochs + baseline",
            "suite": "Epochs tab → epochs.create",
            "status": "ok",
        },
        {
            "eeglab": "Reject epochs (by eye / methods)",
            "suite": "Epoch reject UI not yet (marks only on continuous)",
            "status": "gap",
        },
        {
            "eeglab": "Plot Channel ERPs / ERP image",
            "suite": "Visualizer → ERP (butterfly + channel trace; no ERPimage yet)",
            "status": "partial",
        },
    ]

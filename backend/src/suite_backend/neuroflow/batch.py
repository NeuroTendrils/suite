"""Study-wide batch application of a ProcessingPlan.

Copyright 2026 NeuroTendrils
Proprietary — see LICENSE.

Design contract
---------------
1. **Isolation.** One recording failing never aborts the batch. Every recording
   gets an independent outcome; the caller receives the full report.
2. **Preview before commit.** ``preview_batch`` resolves the target set and runs
   eligibility checks *without* touching the executor, so the UI can show
   "34 eligible, 4 blocked, 2 already processed" before anything is written.
3. **Never silently skip.** A recording that cannot be processed produces a
   ``blocked`` outcome carrying a machine-readable reason code — never a
   quiet omission. This mirrors the import contract (no silent guesses).
4. **Idempotence.** Re-running a plan over a study will, by default, skip
   recordings that already carry an artifact from this exact plan revision.
   Pass ``force=True`` to re-derive.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from suite_backend.domain.models import (
    DatasetArtifact,
    ProcessingPlan,
    Recording,
    Study,
)
from suite_backend.domain.queries import iter_recordings
from suite_backend.neuroflow.plan_executor import execute_plan

Status = Literal["ok", "failed", "blocked", "skipped"]

# Reason codes are stable and machine-readable. The UI maps them to copy;
# never parse the human message.
REASON_NO_EEG = "no_eeg_stream"
REASON_NOT_NORMALIZED = "not_normalized"
REASON_VALIDATION_FAILED = "validation_failed"
REASON_UNSYNCED_MULTISTREAM = "unsynced_multistream"
REASON_ALREADY_PROCESSED = "already_processed"
REASON_EXECUTOR_ERROR = "executor_error"


@dataclass
class RecordingOutcome:
    """Result of applying a plan to exactly one recording."""

    recording_id: str
    subject_id: str
    subject_label: str
    session_id: str
    run_id: str
    status: Status
    reason: str | None = None
    message: str | None = None
    artifact_ids: list[str] = field(default_factory=list)
    duration_ms: int = 0
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "recording_id": self.recording_id,
            "subject_id": self.subject_id,
            "subject_label": self.subject_label,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "status": self.status,
            "reason": self.reason,
            "message": self.message,
            "artifact_ids": self.artifact_ids,
            "duration_ms": self.duration_ms,
            "traceback": self.traceback,
        }


@dataclass
class BatchReport:
    """Aggregate outcome of a batch run. Always complete — never partial."""

    study_id: str
    plan_id: str
    plan_name: str
    outcomes: list[RecordingOutcome] = field(default_factory=list)
    started_at: float = 0.0
    finished_at: float = 0.0
    dry_run: bool = False

    def _count(self, status: Status) -> int:
        return sum(1 for o in self.outcomes if o.status == status)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "plan_id": self.plan_id,
            "plan_name": self.plan_name,
            "dry_run": self.dry_run,
            "totals": {
                "total": self.total,
                "ok": self._count("ok"),
                "failed": self._count("failed"),
                "blocked": self._count("blocked"),
                "skipped": self._count("skipped"),
            },
            "duration_ms": int((self.finished_at - self.started_at) * 1000),
            "outcomes": [o.to_dict() for o in self.outcomes],
        }


# --------------------------------------------------------------------- scope


def resolve_targets(
    study: Study,
    *,
    subject_ids: list[str] | None = None,
    session_ids: list[str] | None = None,
    recording_ids: list[str] | None = None,
    modality: str | None = None,
) -> list[tuple[Any, Any, Any, Recording]]:
    """Resolve a batch scope to concrete recordings.

    Filters are conjunctive and all optional; with none supplied the scope is
    the whole study. An explicit ``recording_ids`` list wins over the tree
    filters so the UI can offer "apply to selection".
    """
    rows = list(iter_recordings(study))

    if recording_ids:
        wanted = set(recording_ids)
        rows = [r for r in rows if r[3].id in wanted]
        missing = wanted - {r[3].id for r in rows}
        if missing:
            raise KeyError(f"recordings not found in study: {sorted(missing)}")
        return rows

    if subject_ids:
        keep = set(subject_ids)
        rows = [r for r in rows if r[0].id in keep]
    if session_ids:
        keep = set(session_ids)
        rows = [r for r in rows if r[1].id in keep]
    if modality:
        rows = [r for r in rows if modality in (r[3].modalities or [])]
    return rows


# ---------------------------------------------------------------- eligibility


def check_eligibility(
    recording: Recording,
    *,
    streams: list[Any],
    plan: ProcessingPlan,
    existing_artifacts: list[DatasetArtifact],
    force: bool = False,
) -> tuple[bool, str | None, str | None]:
    """Return ``(eligible, reason_code, message)`` for one recording.

    Cheap checks only — no signal is loaded here. This runs over an entire
    study during preview, so it must stay O(1) per recording.
    """
    eeg_streams = [s for s in streams if getattr(s, "modality", None) == "eeg"]
    if not eeg_streams:
        return False, REASON_NO_EEG, "no EEG stream attached to this recording"

    if not any(getattr(s, "normalized", False) for s in eeg_streams):
        return (
            False,
            REASON_NOT_NORMALIZED,
            "EEG stream has no canonical form — run recordings.normalize first",
        )

    validation = getattr(recording, "validation", None)
    if validation is not None and getattr(validation, "ok", None) is False:
        return False, REASON_VALIDATION_FAILED, "recording failed validation"

    # Multi-stream recordings must declare how they are aligned. Processing an
    # unsynced multimodal recording silently would produce a result nobody can
    # defend, so it is blocked rather than guessed at.
    if len(streams) > 1 and not getattr(recording, "sync_group_ids", None):
        return (
            False,
            REASON_UNSYNCED_MULTISTREAM,
            "multiple streams with no SyncGroup — create one or scope to EEG only",
        )

    if not force:
        # Artifacts arrive from the executor, which is free to return richer
        # or leaner objects than the domain model. Introspect defensively —
        # a malformed artifact must never crash an eligibility sweep that is
        # running over an entire study.
        for art in existing_artifacts:
            if getattr(art, "recording_id", None) != recording.id:
                continue
            parameters = getattr(art, "parameters", None) or {}
            same_plan = parameters.get("plan_id") == plan.id
            same_rev = parameters.get("plan_revision") == getattr(plan, "revision", None)
            if same_plan and same_rev:
                return (
                    False,
                    REASON_ALREADY_PROCESSED,
                    f"already derived by this plan revision ({getattr(art, 'id', '?')})",
                )

    return True, None, None


# ------------------------------------------------------------------- preview


def preview_batch(
    *,
    study: Study,
    plan: ProcessingPlan,
    repo: Any,
    scope: dict[str, Any] | None = None,
    force: bool = False,
) -> BatchReport:
    """Resolve scope and run eligibility checks without executing anything."""
    scope = scope or {}
    report = BatchReport(
        study_id=study.id,
        plan_id=plan.id,
        plan_name=plan.name,
        dry_run=True,
        started_at=time.time(),
    )
    try:
        existing = repo.list_artifacts(study.id)
    except Exception:  # noqa: BLE001 — optional repo capability
        existing = []

    for subject, session, run, rec in resolve_targets(study, **scope):
        streams = repo.list_streams(study.id, recording_id=rec.id)
        eligible, reason, message = check_eligibility(
            rec,
            streams=streams,
            plan=plan,
            existing_artifacts=existing,
            force=force,
        )
        report.outcomes.append(
            RecordingOutcome(
                recording_id=rec.id,
                subject_id=subject.id,
                subject_label=getattr(subject, "label", subject.id),
                session_id=session.id,
                run_id=run.id,
                status="ok" if eligible else "blocked",
                reason=reason,
                message=message,
            )
        )
    report.finished_at = time.time()
    return report


# ------------------------------------------------------------------- execute


def run_batch(
    *,
    study: Study,
    plan: ProcessingPlan,
    repo: Any,
    scope: dict[str, Any] | None = None,
    force: bool = False,
    stop_on_error: bool = False,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> BatchReport:
    """Apply ``plan`` across the resolved scope, one recording at a time.

    ``progress`` is invoked after each recording with a JSON-serializable dict
    so the caller can stream updates to the UI. Failures are captured per
    recording; the batch continues unless ``stop_on_error`` is set.
    """
    scope = scope or {}
    report = BatchReport(
        study_id=study.id,
        plan_id=plan.id,
        plan_name=plan.name,
        started_at=time.time(),
    )
    try:
        existing = repo.list_artifacts(study.id)
    except Exception:  # noqa: BLE001
        existing = []

    targets = resolve_targets(study, **scope)
    total = len(targets)

    for index, (subject, session, run, rec) in enumerate(targets):
        started = time.time()
        streams = repo.list_streams(study.id, recording_id=rec.id)
        eligible, reason, message = check_eligibility(
            rec, streams=streams, plan=plan, existing_artifacts=existing, force=force
        )

        if not eligible:
            outcome = RecordingOutcome(
                recording_id=rec.id,
                subject_id=subject.id,
                subject_label=getattr(subject, "label", subject.id),
                session_id=session.id,
                run_id=run.id,
                status="skipped" if reason == REASON_ALREADY_PROCESSED else "blocked",
                reason=reason,
                message=message,
            )
        else:
            try:
                artifacts = execute_plan(
                    study_id=study.id, plan=plan, recording=rec, repo=repo
                )
                outcome = RecordingOutcome(
                    recording_id=rec.id,
                    subject_id=subject.id,
                    subject_label=getattr(subject, "label", subject.id),
                    session_id=session.id,
                    run_id=run.id,
                    status="ok",
                    artifact_ids=[a.id for a in artifacts],
                )
                existing.extend(artifacts)
            except Exception as exc:  # noqa: BLE001 — per-recording isolation
                outcome = RecordingOutcome(
                    recording_id=rec.id,
                    subject_id=subject.id,
                    subject_label=getattr(subject, "label", subject.id),
                    session_id=session.id,
                    run_id=run.id,
                    status="failed",
                    reason=REASON_EXECUTOR_ERROR,
                    message=str(exc),
                    traceback=traceback.format_exc(limit=12),
                )

        outcome.duration_ms = int((time.time() - started) * 1000)
        report.outcomes.append(outcome)

        if progress is not None:
            progress(
                {
                    "index": index + 1,
                    "total": total,
                    "recording_id": rec.id,
                    "subject_label": getattr(subject, "label", subject.id),
                    "status": outcome.status,
                }
            )

        if stop_on_error and outcome.status == "failed":
            break

    report.finished_at = time.time()
    return report


def iter_failures(report: BatchReport) -> Iterator[RecordingOutcome]:
    """Yield outcomes a researcher must act on (failed or blocked)."""
    for outcome in report.outcomes:
        if outcome.status in ("failed", "blocked"):
            yield outcome

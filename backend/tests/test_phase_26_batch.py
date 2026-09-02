"""Phase 26 — study-wide batch application.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from suite_backend.neuroflow import batch as B


# ------------------------------------------------------------------ fixtures


def _stream(modality="eeg", normalized=True):
    return SimpleNamespace(id=f"stream_{modality}", modality=modality, normalized=normalized)


def _rec(rid, *, modalities=("eeg",), sync=(), validation_ok=True):
    return SimpleNamespace(
        id=rid,
        modalities=list(modalities),
        sync_group_ids=list(sync),
        validation=SimpleNamespace(ok=validation_ok),
    )


def _study(recordings_per_subject=2, subjects=3):
    subs = []
    for s in range(subjects):
        recs = [_rec(f"rec_{s}_{r}") for r in range(recordings_per_subject)]
        run = SimpleNamespace(id=f"run_{s}", name="run-01", recordings=recs)
        ses = SimpleNamespace(id=f"ses_{s}", name="ses-01", runs=[run])
        subs.append(SimpleNamespace(id=f"sub_{s}", label=f"S0{s}", sessions=[ses]))
    return SimpleNamespace(id="study_1", subjects=subs)


class FakeRepo:
    """Minimal repo double honouring the surface batch.py depends on."""

    def __init__(self, streams_for=None, artifacts=None):
        self._streams_for = streams_for or {}
        self._artifacts = artifacts or []

    def list_streams(self, _study_id, recording_id=None):
        return self._streams_for.get(recording_id, [_stream()])

    def list_artifacts(self, _study_id):
        return list(self._artifacts)


class FakePlan:
    id = "plan_1"
    name = "test plan"
    revision = 1
    steps = []


# -------------------------------------------------------------------- scope


def test_resolve_targets_defaults_to_whole_study():
    study = _study()
    assert len(B.resolve_targets(study)) == 6


def test_resolve_targets_filters_by_subject():
    study = _study()
    rows = B.resolve_targets(study, subject_ids=["sub_1"])
    assert {r[3].id for r in rows} == {"rec_1_0", "rec_1_1"}


def test_explicit_recording_ids_win_over_tree_filters():
    study = _study()
    rows = B.resolve_targets(study, subject_ids=["sub_0"], recording_ids=["rec_2_1"])
    assert [r[3].id for r in rows] == ["rec_2_1"]


def test_unknown_recording_id_raises_rather_than_silently_dropping():
    study = _study()
    with pytest.raises(KeyError, match="not found"):
        B.resolve_targets(study, recording_ids=["rec_0_0", "nope"])


# -------------------------------------------------------------- eligibility


def test_recording_without_eeg_is_blocked():
    ok, reason, _ = B.check_eligibility(
        _rec("r"), streams=[_stream("emg")], plan=FakePlan(), existing_artifacts=[]
    )
    assert not ok and reason == B.REASON_NO_EEG


def test_unnormalized_recording_is_blocked():
    ok, reason, _ = B.check_eligibility(
        _rec("r"),
        streams=[_stream("eeg", normalized=False)],
        plan=FakePlan(),
        existing_artifacts=[],
    )
    assert not ok and reason == B.REASON_NOT_NORMALIZED


def test_multistream_without_syncgroup_is_blocked_not_guessed():
    ok, reason, _ = B.check_eligibility(
        _rec("r", modalities=("eeg", "emg")),
        streams=[_stream("eeg"), _stream("emg")],
        plan=FakePlan(),
        existing_artifacts=[],
    )
    assert not ok and reason == B.REASON_UNSYNCED_MULTISTREAM


def test_multistream_with_syncgroup_is_eligible():
    ok, _, _ = B.check_eligibility(
        _rec("r", modalities=("eeg", "emg"), sync=("sync_1",)),
        streams=[_stream("eeg"), _stream("emg")],
        plan=FakePlan(),
        existing_artifacts=[],
    )
    assert ok


def test_already_processed_is_skipped_unless_forced():
    art = SimpleNamespace(
        id="art_1", recording_id="r", parameters={"plan_id": "plan_1", "plan_revision": 1}
    )
    ok, reason, _ = B.check_eligibility(
        _rec("r"), streams=[_stream()], plan=FakePlan(), existing_artifacts=[art]
    )
    assert not ok and reason == B.REASON_ALREADY_PROCESSED

    ok_forced, _, _ = B.check_eligibility(
        _rec("r"), streams=[_stream()], plan=FakePlan(), existing_artifacts=[art], force=True
    )
    assert ok_forced


# ------------------------------------------------------------------ preview


def test_preview_writes_nothing_and_reports_every_recording():
    study = _study()
    report = B.preview_batch(study=study, plan=FakePlan(), repo=FakeRepo())
    d = report.to_dict()
    assert d["dry_run"] is True
    assert d["totals"]["total"] == 6
    assert len(d["outcomes"]) == 6


# ------------------------------------------------------------------ execute


def test_one_failure_does_not_abort_the_batch(monkeypatch):
    study = _study(subjects=1, recordings_per_subject=3)

    calls = {"n": 0}

    def flaky(**_kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("filter blew up")
        return [SimpleNamespace(id=f"art_{calls['n']}")]

    monkeypatch.setattr(B, "execute_plan", flaky)
    report = B.run_batch(study=study, plan=FakePlan(), repo=FakeRepo())
    totals = report.to_dict()["totals"]

    assert totals["total"] == 3
    assert totals["ok"] == 2
    assert totals["failed"] == 1
    assert calls["n"] == 3  # it kept going after the failure


def test_stop_on_error_halts_early(monkeypatch):
    study = _study(subjects=1, recordings_per_subject=3)
    monkeypatch.setattr(
        B, "execute_plan", lambda **_k: (_ for _ in ()).throw(RuntimeError("nope"))
    )
    report = B.run_batch(study=study, plan=FakePlan(), repo=FakeRepo(), stop_on_error=True)
    assert report.total == 1


def test_failure_outcome_carries_a_traceback(monkeypatch):
    study = _study(subjects=1, recordings_per_subject=1)
    monkeypatch.setattr(
        B, "execute_plan", lambda **_k: (_ for _ in ()).throw(ValueError("bad montage"))
    )
    report = B.run_batch(study=study, plan=FakePlan(), repo=FakeRepo())
    out = report.outcomes[0]
    assert out.status == "failed"
    assert out.reason == B.REASON_EXECUTOR_ERROR
    assert "bad montage" in out.message
    assert out.traceback and "ValueError" in out.traceback


def test_progress_callback_fires_once_per_recording(monkeypatch):
    study = _study(subjects=2, recordings_per_subject=2)
    monkeypatch.setattr(B, "execute_plan", lambda **_k: [SimpleNamespace(id="a")])
    seen = []
    B.run_batch(study=study, plan=FakePlan(), repo=FakeRepo(), progress=seen.append)
    assert len(seen) == 4
    assert seen[-1]["index"] == 4 and seen[-1]["total"] == 4


def test_iter_failures_surfaces_only_actionable_outcomes(monkeypatch):
    study = _study(subjects=1, recordings_per_subject=2)
    repo = FakeRepo(streams_for={"rec_0_0": [_stream("emg")]})
    monkeypatch.setattr(B, "execute_plan", lambda **_k: [SimpleNamespace(id="a")])
    report = B.run_batch(study=study, plan=FakePlan(), repo=repo)
    failures = list(B.iter_failures(report))
    assert len(failures) == 1
    assert failures[0].reason == B.REASON_NO_EEG

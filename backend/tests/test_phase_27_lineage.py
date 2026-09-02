"""Phase 27 — lineage chain and history replay.

Copyright 2026 NeuroTendrils
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from suite_backend.neuroflow import lineage as L

BASE = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def art(aid, op, *, parent=None, seconds=0, paths=None, params=None, rec="rec_1"):
    return SimpleNamespace(
        id=aid,
        operation=op,
        parent_id=parent,
        recording_id=rec,
        parameters=params or {},
        paths=paths if paths is not None else {"fif": f"/w/{aid}.fif"},
        checksum=f"sum_{aid}",
        created_at=BASE + timedelta(seconds=seconds),
    )


# ------------------------------------------------------------------ ordering


def test_chain_follows_parent_links_not_timestamps():
    # Deliberately shuffled, and b/c share a timestamp so sorting by time alone
    # would be non-deterministic.
    arts = [
        art("c", "notch", parent="b", seconds=5),
        art("a", "import", seconds=0),
        art("b", "highpass", parent="a", seconds=5),
    ]
    assert [a.id for a in L.order_chain(arts)] == ["a", "b", "c"]


def test_multiple_roots_order_by_time():
    arts = [art("z", "import", seconds=9), art("a", "import", seconds=1)]
    assert [a.id for a in L.order_chain(arts)] == ["a", "z"]


def test_parent_cycle_does_not_hang_and_loses_nothing():
    arts = [art("a", "filter", parent="b"), art("b", "filter", parent="a")]
    out = L.order_chain(arts)
    assert len(out) == 2
    assert {a.id for a in out} == {"a", "b"}


def test_parent_outside_the_set_is_treated_as_a_root():
    arts = [art("a", "filter", parent="from_another_study")]
    assert [a.id for a in L.order_chain(arts)] == ["a"]


# --------------------------------------------------------------------- chain


def test_chain_only_includes_this_recording():
    rec = SimpleNamespace(id="rec_1")
    arts = [art("a", "import"), art("b", "filter", rec="rec_2")]
    steps = L.build_chain(rec, arts)
    assert [s["id"] for s in steps] == ["a"]


def test_human_steps_are_marked_distinctly():
    rec = SimpleNamespace(id="rec_1")
    arts = [
        art("a", "highpass", params={"freq": 1}),
        art("b", "mark_bad_channels", parent="a", params={"channels": ["T8", "P7"]}),
    ]
    steps = L.build_chain(rec, arts)
    assert steps[0]["kind"] == "filter"
    assert steps[1]["kind"] == "human"


def test_unknown_operation_keeps_its_name_instead_of_disappearing():
    rec = SimpleNamespace(id="rec_1")
    steps = L.build_chain(rec, [art("a", "some_new_op")])
    assert steps[0]["label"] == "some_new_op"


def test_step_without_a_signal_artifact_is_flagged_unreplayable():
    rec = SimpleNamespace(id="rec_1")
    steps = L.build_chain(rec, [art("a", "mark_bad_channels", paths={})])
    assert steps[0]["replayable"] is False


@pytest.mark.parametrize(
    "op,params,expected",
    [
        ("highpass", {"freq": 1}, "1 Hz"),
        ("bandpass", {"l_freq": 1, "h_freq": 40}, "1–40 Hz"),
        ("notch", {"freq": 60}, "60 Hz"),
        ("mark_bad_channels", {"channels": ["T8", "P7"]}, "2 flagged"),
        ("ica_exclude", {"exclude": [0, 3]}, "−2 comp"),
        ("epochs", {"n_epochs": 240}, "240 trials"),
        ("average_reference", {}, "average"),
        ("unknown_op", {"x": 1}, ""),
    ],
)
def test_parameter_summaries(op, params, expected):
    assert L.describe_parameters(op, params) == expected


# -------------------------------------------------------------------- replay


class FakeStream:
    def __init__(self):
        self.id = "stream_1"
        self.modality = "eeg"
        self.sample_paths = {"fif": "/w/head.fif"}
        self.provenance = {"created_by": "import"}

    def model_copy(self, deep=False):
        clone = FakeStream()
        clone.sample_paths = dict(self.sample_paths)
        clone.provenance = dict(self.provenance)
        return clone


def test_replay_points_at_the_artifact_and_leaves_the_original_alone():
    rec = SimpleNamespace(id="rec_1")
    original = FakeStream()
    replay = L.stream_at_artifact(rec, [original], art("b", "notch"))

    assert replay.sample_paths["fif"] == "/w/b.fif"
    assert replay.provenance["replay_of"] == "b"
    assert replay.provenance["read_only"] is True
    # The live stream must be untouched — viewing history cannot mutate a study.
    assert original.sample_paths["fif"] == "/w/head.fif"
    assert "replay_of" not in original.provenance


def test_replaying_a_step_with_no_signal_raises_clearly():
    rec = SimpleNamespace(id="rec_1")
    with pytest.raises(ValueError, match="nothing to replay"):
        L.stream_at_artifact(rec, [FakeStream()], art("a", "mark_bad_channels", paths={}))


def test_replay_without_any_stream_raises():
    rec = SimpleNamespace(id="rec_1")
    with pytest.raises(KeyError):
        L.stream_at_artifact(rec, [], art("a", "notch"))

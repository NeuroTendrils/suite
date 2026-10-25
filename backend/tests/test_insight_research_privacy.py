from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from suite_backend.app_context import AppContext
from suite_backend.devices.cortex import capture_insight, eeg_row
from suite_backend.domain.models import DataSplit, MLDataset
from suite_backend.ipc.handlers.insight_cmds import CaptureParams, capture
from suite_backend.neuroflow.ica_ops import _fit_ica
from suite_backend.neurostudio.contracts import validate_split
from suite_backend.neurostudio.evaluation import evaluate
from suite_backend.neurostudio.export import export_study_package
from suite_backend.neurostudio.inference import run_inference
from suite_backend.neurostudio.model_training import train
from suite_backend.scientific.algorithms.feature_extraction import _bandpower_1d
from suite_backend.scientific.algorithms.splits import make_stratified_trial_split
from suite_backend.scientific.io.importers import get_default_registry
from suite_backend.scientific.io.insight import CHANNELS
from suite_backend.storage.local import LocalWorkspace
from tests.test_phase_22_infer import _trained


def insight_csv(path: Path, *, gap=False):
    lines = [
        "EMOTIV Insight,sampling rate:128,units:uV",
        "Timestamp,EEG.AF4,EEG.T7,EEG.Pz,EEG.T8,EEG.AF3,INTERPOLATED,CQ_AF3,MarkerValueInt",
    ]
    for i in range(256):
        lines.append(
            f"{1000 + i / 128 + (0.1 if gap and i > 127 else 0)},5,2,3,4,1,{int(i == 30)},4,{int(i == 64)}"
        )
    path.write_text("\n".join(lines))


def test_insight_import_maps_order_units_and_artifacts(tmp_path):
    path = tmp_path / "eeg.csv"
    insight_csv(path, gap=True)
    importer = get_default_registry().find(path)
    assert importer.name == "emotiv_insight"
    assert importer.inspect(path)["sfreq"] == 128
    rec, _, raw = importer.import_recording(
        path, subject_id="s", session_id="v", run_id="r", sfreq=128, artifact_dir=tmp_path / "art"
    )
    assert raw.ch_names == list(CHANNELS)
    np.testing.assert_allclose(raw.get_data()[:, 0], np.arange(1, 6) * 1e-6)
    assert rec.channel_count == 5
    assert rec.acquisition_metadata["timestamp_gaps"] == 1
    assert "BAD_interpolated" in raw.annotations.description
    assert "BAD boundary" in raw.annotations.description
    assert "marker/1" in raw.annotations.description
    assert Path(rec.source_files[0]).exists()
    with pytest.raises(ValueError, match="128"):
        importer.import_recording(path, subject_id="s", session_id="v", run_id="r", sfreq=256)


def test_cortex_mapping_uses_subscription_columns():
    cols = ["INTERPOLATED", "AF4", "T8", "Pz", "T7", "AF3"]
    assert eeg_row({"sid": "s", "time": 1, "eeg": [0, 5, 4, 3, 2, 1]}, cols, "s") == [
        1,
        0,
        1,
        2,
        3,
        4,
        5,
    ]
    assert eeg_row({"sid": "other", "eeg": []}, cols, "s") is None
    with pytest.raises(ValueError):
        eeg_row({"sid": "s", "time": 1, "eeg": [0, float("nan"), 4, 3, 2, 1]}, cols, "s")


class FakeSocket:
    def __init__(self, *, deny=False, no_eeg=False):
        self.requests = []
        self.pending = None
        self.i = 0
        self.closed = False
        self.deny = deny
        self.no_eeg = no_eeg

    def send(self, payload):
        req = json.loads(payload)
        self.requests.append(req)
        self.pending = req

    def recv(self, timeout):
        if self.pending:
            req, self.pending = self.pending, None
            result = {
                "requestAccess": {"accessGranted": not self.deny},
                "authorize": {"cortexToken": "TOP_SECRET_TOKEN"},
                "queryHeadsets": [
                    {
                        "id": "INSIGHT-123",
                        "status": "connected",
                        "sensors": list(CHANNELS),
                        "settings": {"eegRate": 128},
                    }
                ],
                "createSession": {"id": "session"},
                "subscribe": {
                    "success": []
                    if self.no_eeg
                    else [{"streamName": "eeg", "cols": ["INTERPOLATED", *CHANNELS]}]
                },
                "updateSession": {},
            }[req["method"]]
            return json.dumps({"id": req["id"], "result": result})
        self.i += 1
        return json.dumps(
            {"sid": "session", "time": 1700000000 + self.i / 128, "eeg": [0, 1, 2, 3, 4, 5]}
        )

    def close(self):
        self.closed = True


def test_capture_local_tls_cleanup_and_no_persisted_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("EMOTIV_CLIENT_ID", "private-client")
    monkeypatch.setenv("EMOTIV_CLIENT_SECRET", "private-secret")
    socket = FakeSocket()

    def connect(url, **kwargs):
        assert url == "wss://localhost:6868"
        assert kwargs["ssl"].check_hostname
        assert kwargs["proxy"] is None
        return socket

    out = capture_insight(tmp_path, 2, connect_fn=connect)
    assert out["n_samples"] == 256
    assert socket.closed
    assert socket.requests[-1]["method"] == "updateSession"
    text = Path(out["path"]).read_text()
    for secret in ("private-client", "private-secret", "TOP_SECRET_TOKEN"):
        assert secret not in text
    assert Path(out["path"]).stat().st_mode & 0o777 == 0o600
    assert get_default_registry().find(out["path"]).name == "emotiv_insight"


@pytest.mark.parametrize("deny,no_eeg", [(True, False), (False, True)])
def test_failed_capture_closes_socket_without_writing(tmp_path, monkeypatch, deny, no_eeg):
    monkeypatch.setenv("EMOTIV_CLIENT_ID", "id")
    monkeypatch.setenv("EMOTIV_CLIENT_SECRET", "secret")
    socket = FakeSocket(deny=deny, no_eeg=no_eeg)
    with pytest.raises(ValueError):
        capture_insight(tmp_path, 2, connect_fn=lambda *a, **kw: socket)
    assert socket.closed
    assert not list(tmp_path.iterdir())


def test_capture_requires_consent_before_network(tmp_path):
    ctx = AppContext(tmp_path)
    with pytest.raises(ValueError, match="consent"):
        capture(CaptureParams(study_id="unknown"), ctx)


def test_welch_absolute_power_and_band_isolation():
    t = np.arange(1280) / 128
    signal = 2 * np.sin(2 * np.pi * 10 * t)
    assert _bandpower_1d(signal, 128, 8, 13) == pytest.approx(2, rel=0.01)
    assert _bandpower_1d(signal, 128, 20, 30) < 1e-10


def test_ica_caps_components_to_five_eeg_channels():
    import mne

    raw = mne.io.RawArray(
        np.random.default_rng(42).normal(size=(6, 1024)),
        mne.create_info([*CHANNELS, "marker"], 128, ["eeg"] * 5 + ["stim"]),
        verbose=False,
    )
    ica = _fit_ica(raw, 15)
    assert ica.n_components_ == 5


def test_split_overlap_and_wrong_dataset_rejected():
    ds = MLDataset(study_id="s", n_samples=3)
    sp = DataSplit(study_id="s", dataset_id=ds.id, train_indices=[0, 1], test_indices=[1, 2])
    with pytest.raises(ValueError, match="overlap"):
        validate_split(sp, ds, 3)
    sp.dataset_id = "other"
    with pytest.raises(ValueError, match="different dataset"):
        validate_split(sp, ds, 3)


def test_zero_test_fraction_and_invalid_fraction():
    ds = MLDataset(study_id="s", labels=["a"] * 5 + ["b"] * 5, subject_ids=["s"] * 10)
    assert not make_stratified_trial_split(ds, study_id="s", test_frac=0, val_frac=0).test_indices
    with pytest.raises(ValueError, match="fractions"):
        make_stratified_trial_split(ds, study_id="s", test_frac=float("nan"))


def test_inference_rejects_same_width_reordered_features(tmp_path):
    ctx, sid, ds, _sp, exp = _trained(tmp_path)
    dataset = ctx.studies.get_mldataset(sid, ds["id"])
    dataset.feature_names.reverse()
    ctx.studies.save_mldataset(sid, dataset)
    with pytest.raises(ValueError, match="names/order"):
        run_inference(study_id=sid, experiment_id=exp["id"], ctx=ctx)


def test_eval_does_not_hide_unseen_labels_or_fallback(tmp_path):
    ctx, sid, ds, sp, exp = _trained(tmp_path)
    dataset = ctx.studies.get_mldataset(sid, ds["id"])
    y = np.load(dataset.paths["y"]).astype("U20")
    test = sp["test_indices"]
    y[test] = "unseen"
    np.save(dataset.paths["y"], y)
    out = evaluate(study_id=sid, experiment_id=exp["id"], ctx=ctx)
    assert out["metrics"]["n"] == len(test)
    assert out["metrics"]["accuracy"] == 0
    assert "unseen" in out["metrics"]["classes"]
    split = ctx.studies.get_split(sid, sp["id"])
    split.test_indices = []
    ctx.studies.save_split(sid, split)
    out = evaluate(study_id=sid, experiment_id=exp["id"], ctx=ctx)
    assert out["status"] == "error"
    assert "empty" in out["message"]


def test_auto_training_keeps_test_out_of_scaler(tmp_path):
    import joblib

    ctx, sid, ds, sp, exp = _trained(tmp_path)
    experiment = ctx.studies.get_experiment(sid, exp["id"])
    experiment.template_id = "research_auto"
    ctx.studies.save_experiment(sid, experiment)
    out = train(study_id=sid, experiment_id=exp["id"], ctx=ctx)
    assert out["status"] == "ok"
    bundle = joblib.load(out["model"]["paths"]["joblib"])
    X = np.load(ds["paths"]["X"])
    np.testing.assert_allclose(
        bundle["pipeline"].named_steps["scaler"].mean_, X[sp["train_indices"]].mean(axis=0)
    )
    assert out["model"]["metadata"]["train_indices"] == sp["train_indices"]


def test_exports_redact_by_default_and_metadata_only_excludes_binaries(tmp_path):
    ctx = AppContext(tmp_path / "ws")
    study = ctx.studies.create_study("PRIVATE PERSON")
    root = ctx.workspace.study_dir(study.id)
    (root / "models" / "private.joblib").write_bytes(b"SENSITIVE MODEL")
    (root / "artifacts" / "eeg.fif.gz").write_bytes(b"SENSITIVE EEG")
    (root / "private.csv").write_text("SENSITIVE EEG")
    (root / "reports" / "private.md").write_text("PRIVATE PERSON")
    package = export_study_package(study_id=study.id, ctx=ctx, include_samples=True)
    with zipfile.ZipFile(package["path"]) as archive:
        assert set(archive.namelist()) == {"summary.json", "privacy.json"}
        assert (
            "PRIVATE PERSON" not in b"".join(archive.read(n) for n in archive.namelist()).decode()
        )
    package = export_study_package(study_id=study.id, ctx=ctx, deidentify=False)
    with zipfile.ZipFile(package["path"]) as archive:
        assert all(n.endswith(".json") for n in archive.namelist())


def test_workspace_rejects_prefix_sibling_and_traversal(tmp_path):
    workspace = LocalWorkspace(tmp_path / "ws")
    with pytest.raises(ValueError, match="escapes"):
        workspace.ensure_inside(tmp_path / "ws-other" / "private")
    with pytest.raises(ValueError, match="invalid"):
        workspace.study_dir("../../other")

from __future__ import annotations

from pathlib import Path

import numpy as np

from suite_backend.scientific.io.text_matrix import import_text_recording, inspect_text_matrix


def test_inspect_and_import_txt(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    data = rng.normal(size=(500, 4))  # samples x channels
    path = tmp_path / "raw.txt"
    header = "Fz Cz Pz Oz"
    body = "\n".join(" ".join(f"{v:.6f}" for v in row) for row in data)
    path.write_text(header + "\n" + body, encoding="utf-8")

    info = inspect_text_matrix(path)
    assert info["status"] == "ok"
    assert info["n_rows"] == 500
    assert info["n_cols"] == 4
    assert info["has_header"] is True
    assert len(info["columns"]) == 4

    art_dir = tmp_path / "arts"
    recording, artifact, raw = import_text_recording(
        path,
        subject_id="sub",
        session_id="ses",
        run_id="run",
        sfreq=250.0,
        montage="standard_1020",
        artifact_dir=art_dir,
    )
    assert recording.source_format == "text_matrix"
    assert recording.sampling_rate == 250.0
    assert recording.channel_count == 4
    assert recording.channels[0].name == "Fz"
    assert recording.channels[0].location is not None
    assert Path(artifact.paths["fif"]).exists()
    assert raw.n_times == 500


def test_column_selection_drops_extra_columns(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    # 32 EEG + time + stim
    eeg = rng.normal(size=(200, 32))
    time = np.arange(200)[:, None] / 250.0
    stim = np.zeros((200, 1))
    stim[50, 0] = 1
    data = np.hstack([eeg, time, stim])
    path = tmp_path / "wide.txt"
    np.savetxt(path, data, fmt="%.6f")

    info = inspect_text_matrix(path)
    assert info["n_cols"] == 34
    # Without name heuristics, all numeric columns default to EEG — user picks roles.
    assert len(info["columns"]) == 34

    selection = [
        {"index": i, "name": f"E{i + 1}", "role": "eeg"} for i in range(32)
    ] + [
        {"index": 32, "name": "time", "role": "time"},
        {"index": 33, "name": "Marker", "role": "stim"},
    ]
    recording, _artifact, raw = import_text_recording(
        path,
        subject_id="sub",
        session_id="ses",
        run_id="run",
        sfreq=250.0,
        column_selection=selection,
        montage="biosemi32",
    )
    # 32 eeg + 1 stim kept; time ignored
    assert recording.channel_count == 33
    assert raw.get_channel_types().count("eeg") == 32
    assert raw.get_channel_types().count("stim") == 1
    # stim column → Event markers (same role as .set annotations in the timeline)
    assert len(recording.events) >= 1
    assert abs(recording.events[0].timestamp - (50 / 250.0)) < 1e-6
    assert recording.events[0].name in {"1", "Marker", "stim"}

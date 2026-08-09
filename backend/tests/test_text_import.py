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

    art_dir = tmp_path / "arts"
    recording, artifact, raw = import_text_recording(
        path,
        subject_id="sub",
        session_id="ses",
        run_id="run",
        sfreq=250.0,
        artifact_dir=art_dir,
    )
    assert recording.source_format == "text_matrix"
    assert recording.sampling_rate == 250.0
    assert recording.channel_count == 4
    assert recording.channels[0].name == "Fz"
    assert Path(artifact.paths["fif"]).exists()
    assert raw.n_times == 500

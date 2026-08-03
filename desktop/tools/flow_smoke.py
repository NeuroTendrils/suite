"""Dev-only: exercise the NeuroFlow stages end to end against a temp project."""

from __future__ import annotations

import sys
import time
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DESKTOP))

from neurotendrils.runtime import ensure_sys_path  # noqa: E402

ensure_sys_path()

from PySide6.QtWidgets import QApplication  # noqa: E402

PROJECT = DESKTOP / ".ui-screens" / "smoke-project"


def make_recording() -> Path:
    import mne
    import numpy as np

    for name in ("datasets", "plans", "models", "runs"):
        (PROJECT / name).mkdir(parents=True, exist_ok=True)
    target = PROJECT / "datasets" / "smoke_raw.fif"
    if target.exists():
        return target
    rng = np.random.default_rng(0)
    info = mne.create_info(["Fz", "Cz", "Pz", "Oz"], 250.0, "eeg")
    raw = mne.io.RawArray(rng.normal(size=(4, 250 * 20)) * 1e-5, info, verbose="ERROR")
    raw.save(str(target), overwrite=True, verbose="ERROR")
    return target


def main() -> int:
    print("building recording", flush=True)
    recording = make_recording()

    app = QApplication(sys.argv)
    from neurotendrils.core.projectdir import ProjectDir
    from neurotendrils.core.theme import Theme

    Theme.instance().initialize(app)
    ProjectDir.instance().set_root(str(PROJECT), persist=False)

    from neurotendrils.mainwindow import MainWindow

    window = MainWindow()
    window.resize(1360, 860)
    window.show()

    def settle(cycles: int = 30) -> None:
        for _ in range(cycles):
            app.processEvents()
            time.sleep(0.01)

    def wait(label: str, pred, seconds: float = 30.0) -> bool:  # noqa: ANN001
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
            if pred():
                print(f"{label}: ok", flush=True)
                return True
        print(f"{label}: TIMEOUT", flush=True)
        return False

    settle()
    window.navigate("flow")
    settle()
    page = window.flow
    page.set_dataset_path(str(recording), False)
    print("stage after select:", page.flow.current_key(), flush=True)
    wait("fingerprint", lambda: bool(page._fingerprint))
    print("steps:", len(page._plan.get("steps") or []), flush=True)
    print("context:", page._context_items(), flush=True)

    page.run_plan()
    print("stage after run start:", page.flow.current_key(), flush=True)
    wait("run", lambda: page._run_done or "fail" in page._run_status.text().lower(), 60)
    print("run status:", page._run_status.text(), flush=True)
    print("run output:", page._run_output, flush=True)

    window.navigate("studio")
    settle()
    studio = window.studio
    studio.set_dataset(page._run_output)
    print(
        "studio stage:",
        studio.flow.current_key(),
        "template:",
        studio._selected_template,
        flush=True,
    )
    print("studio context:", studio._context_items(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

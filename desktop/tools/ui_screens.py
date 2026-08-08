"""Dev-only: render the app shell to PNGs against a seeded sample project.

Usage:
    QT_QPA_PLATFORM=offscreen python tools/ui_screens.py

Output lands in ``desktop/.ui-screens/`` (git-ignored).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DESKTOP))

from neurotendrils.runtime import ensure_sys_path  # noqa: E402

ensure_sys_path()

from PySide6.QtWidgets import QApplication  # noqa: E402

WORKDIR = DESKTOP / ".ui-screens"
PROJECT = WORKDIR / "sample-project"
OUT = WORKDIR / "shots"

_PLANS = {
    "alpha-band-clean.json": ("Alpha band clean", 5),
    "motor-imagery-prep.json": ("Motor imagery prep", 7),
    "resting-state-baseline.json": ("Resting state baseline", 4),
}
_DATASETS = {
    "sub-01_task-rest.edf": 4_600_000,
    "sub-02_task-motor.edf": 7_300_000,
    "sub-03_task-rest.bdf": 2_100_000,
}
_MODELS = {
    "mi-csp-lda": ("Motor imagery CSP+LDA", "csp_lda", 0.874, 0.861),
    "rest-eyes-closed": ("Resting eyes-closed SVM", "riemann_svm", 0.912, 0.903),
}
_RUNS = {"run-20260728-141200.json": 24_000, "run-20260726-093010.json": 18_400}


def seed() -> None:
    for name in ("plans", "datasets", "models", "runs"):
        (PROJECT / name).mkdir(parents=True, exist_ok=True)

    for filename, (title, steps) in _PLANS.items():
        (PROJECT / "plans" / filename).write_text(
            json.dumps(
                {
                    "name": title,
                    "dataset_path": str(PROJECT / "datasets" / "sub-01_task-rest.edf"),
                    "steps": [{"id": f"step{i}"} for i in range(steps)],
                }
            ),
            encoding="utf-8",
        )

    for filename, size in _DATASETS.items():
        path = PROJECT / "datasets" / filename
        if not path.exists() or path.stat().st_size != size:
            path.write_bytes(b"0" * size)

    for folder, (title, template, accuracy, balanced) in _MODELS.items():
        model_dir = PROJECT / "models" / folder
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "model.onnx").write_bytes(b"0" * 1_800_000)
        (model_dir / "model.json").write_text(
            json.dumps(
                {
                    "kind": "neurostudio_model",
                    "title": title,
                    "template_id": template,
                    "format": "onnx",
                    "artifact": "model.onnx",
                    "exported_at": "2026-07-28T14:12:00Z",
                    "metrics": {"accuracy": accuracy, "balanced_accuracy": balanced},
                    "publish": {"status": "local"},
                }
            ),
            encoding="utf-8",
        )

    for filename, size in _RUNS.items():
        (PROJECT / "runs" / filename).write_bytes(b"0" * size)


def seed_plan(page) -> None:  # noqa: ANN001
    """Give the plan stage real steps without touching the file dialogs."""
    from neurotendrils.core.plans import default_params, make_step, step_catalog

    steps = [
        make_step(defn["id"], default_params(defn["id"]), defn.get("description", ""))
        for defn in step_catalog()[:4]
    ]
    page._plan = {"v": 1, "steps": steps}
    page._plan_user_owned = True
    page.render_plan()
    page._refresh_actions()


def first_template() -> str:
    from neurotendrils.core.studio_io import template_catalog

    return str(template_catalog()[0]["id"])


def main() -> int:
    seed()
    OUT.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    from neurotendrils.core.projectdir import ProjectDir
    from neurotendrils.core.theme import Theme, ThemeMode

    Theme.instance().initialize(app)
    ProjectDir.instance().set_root(str(PROJECT), persist=False)

    from neurotendrils.mainwindow import MainWindow

    window = MainWindow()
    window.resize(1360, 860)
    window.show()

    def settle(cycles: int = 24) -> None:
        for _ in range(cycles):
            app.processEvents()
            time.sleep(0.01)

    def capture(name: str) -> None:
        settle(70)
        window.grab().save(str(OUT / f"{name}.png"))

    for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
        Theme.instance().set_mode(mode)
        suffix = mode.value

        window.navigate("home")
        capture(f"home-{suffix}")

        window.navigate("projects")
        capture(f"projects-{suffix}")

        window.navigate("datasets")
        settle()
        rows = window.datasets._rows.rows()
        if rows:
            rows[0].activated.emit()
        capture(f"datasets-{suffix}")
        window.datasets.clear_selection()

        window.navigate("models")
        window._rail.toggle_expanded()
        capture(f"models-expanded-{suffix}")
        window._rail.toggle_expanded()

        window.navigate("flow")
        capture(f"flow-recording-{suffix}")
        seed_plan(window.flow)
        window.flow.flow.go_to("plan")
        capture(f"flow-plan-{suffix}")
        window.flow.flow.go_to("run")
        capture(f"flow-run-{suffix}")
        window.flow.flow.go_to("recording")

        window.navigate("studio")
        capture(f"studio-data-{suffix}")
        window.studio.select_template(first_template())
        window.studio.flow.go_to("template")
        capture(f"studio-template-{suffix}")
        window.studio.flow.go_to("tune")
        capture(f"studio-tune-{suffix}")
        window.studio.flow.go_to("data")

        window.navigate("cloud")
        capture(f"cloud-{suffix}")

        window.navigate("home")
        window.open_settings()
        capture(f"settings-{suffix}")
        window.modal_host.dismiss()
        settle()

    print(f"wrote {len(list(OUT.glob('*.png')))} images to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

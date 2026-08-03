"""NeuroTendrils desktop entrypoint."""

from __future__ import annotations

import sys

from neurotendrils.runtime import ensure_sys_path


def main(argv: list[str] | None = None) -> int:
    ensure_sys_path()

    from PySide6.QtWidgets import QApplication

    from neurotendrils import __version__
    from neurotendrils.core.projectdir import ProjectDir
    from neurotendrils.core.theme import Theme
    from neurotendrils.mainwindow import MainWindow

    app = QApplication(argv or sys.argv)
    app.setOrganizationName("NeuroTendrils")
    app.setApplicationName("NeuroTendrils")
    app.setApplicationVersion(__version__)

    Theme.instance().initialize(app)
    ProjectDir.instance().initialize()

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

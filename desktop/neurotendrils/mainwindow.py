from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from neurotendrils.modules.hub.page import HubPage
from neurotendrils.modules.neuroflow.page import NeuroFlowPage
from neurotendrils.modules.neurostudio.page import NeuroStudioPage
from neurotendrils.settingsdialog import SettingsPanel
from neurotendrils.widgets.icon_rail import IconRail, RailItem
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.modal_host import ModalHost
from neurotendrils.widgets.motion import crossfade_stack


# Rail order matches pages; Hub is the launch home.
_RAIL_ITEMS = (
    RailItem("flow", "NeuroFlow", Glyph.FLOW),
    RailItem("studio", "NeuroStudio", Glyph.STUDIO),
    RailItem("hub", "Hub", Glyph.HUB),
)
_HUB_INDEX = 2


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NeuroTendrils")
        self.resize(1024, 720)
        self.setMinimumSize(720, 480)
        self._settings: SettingsPanel | None = None

        root = QWidget(self)
        root.setObjectName("appRoot")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._rail = IconRail(list(_RAIL_ITEMS), root)
        self._rail.settingsRequested.connect(self.open_settings)

        self._pages = QStackedWidget(root)
        self._pages.setObjectName("pageStack")
        self._pages.addWidget(NeuroFlowPage(self._pages))
        self._pages.addWidget(NeuroStudioPage(self._pages))
        self._pages.addWidget(HubPage(self._pages))

        layout.addWidget(self._rail)
        layout.addWidget(self._pages, 1)
        self.setCentralWidget(root)

        self.modal_host = ModalHost(root)
        root.setProperty("_ntModalHost", self.modal_host)
        self.setProperty("_ntModalHost", self.modal_host)

        self._pages.setCurrentIndex(_HUB_INDEX)
        self._rail.blockSignals(True)
        self._rail.set_current(_HUB_INDEX)
        self._rail.blockSignals(False)
        self._rail.currentChanged.connect(self._on_nav_changed)

    def _on_nav_changed(self, index: int) -> None:
        crossfade_stack(self._pages, index)

    def open_settings(self) -> None:
        if self._settings is None:
            self._settings = SettingsPanel()
            self._settings.closed.connect(self.modal_host.dismiss)
        self.modal_host.present(
            self._settings,
            dismissible=True,
            own=False,
            max_width=780,
            max_height=560,
        )

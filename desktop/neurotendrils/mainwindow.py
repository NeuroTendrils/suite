from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.modules.cloud.page import CloudPage
from neurotendrils.modules.home.page import HomePage
from neurotendrils.modules.library.page import LibraryPage
from neurotendrils.modules.neuroflow.page import RECORDING as FLOW_RECORDING
from neurotendrils.modules.neuroflow.page import NeuroFlowPage
from neurotendrils.modules.neurostudio.page import TRAIN as STUDIO_TRAIN
from neurotendrils.modules.neurostudio.page import NeuroStudioPage
from neurotendrils.settingsdialog import SettingsPanel
from neurotendrils.widgets import modals
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.modal_host import ModalHost
from neurotendrils.widgets.motion import crossfade_stack
from neurotendrils.widgets.nav_rail import NavItem, NavRail
from neurotendrils.widgets.top_bar import TopBar

_NAV_ITEMS = (
    NavItem("home", "Home", Glyph.HOME),
    NavItem("projects", "Projects", Glyph.PROJECTS),
    NavItem("datasets", "Datasets", Glyph.DATASETS),
    NavItem("models", "Models", Glyph.MODELS),
    NavItem("flow", "NeuroFlow", Glyph.FLOW),
    NavItem("studio", "NeuroStudio", Glyph.STUDIO),
    NavItem("cloud", "Cloud", Glyph.CLOUD),
)
_FOOTER_ITEMS = (NavItem("settings", "Settings", Glyph.SETTINGS),)


@dataclass(frozen=True)
class _Route:
    index: int
    title: str


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NeuroTendrils")
        self.resize(1280, 800)
        self.setMinimumSize(880, 560)
        self._settings: SettingsPanel | None = None

        root = QWidget(self)
        root.setObjectName("appRoot")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self._rail = NavRail(list(_NAV_ITEMS), list(_FOOTER_ITEMS), root)

        workspace = QWidget(root)
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        self._top_bar = TopBar(workspace)
        self._pages = QStackedWidget(workspace)
        self._pages.setObjectName("pageStack")

        self.home = HomePage(self._pages)
        self.projects = LibraryPage(
            "plan",
            "Projects",
            "Preprocessing pipelines saved in this project folder.",
            "New pipeline",
            self._pages,
        )
        self.datasets = LibraryPage(
            "dataset",
            "Datasets",
            "Recordings imported into this project folder.",
            "Import recording",
            self._pages,
        )
        self.models = LibraryPage(
            "model",
            "Models",
            "Models trained and exported from this project.",
            "Train model",
            self._pages,
        )
        self.flow = NeuroFlowPage(self._pages)
        self.studio = NeuroStudioPage(self._pages)
        self.cloud = CloudPage(self._pages)

        self._routes: dict[str, _Route] = {}
        for key, page, title in (
            ("home", self.home, "Home"),
            ("projects", self.projects, "Projects"),
            ("datasets", self.datasets, "Datasets"),
            ("models", self.models, "Models"),
            ("flow", self.flow, "NeuroFlow"),
            ("studio", self.studio, "NeuroStudio"),
            ("cloud", self.cloud, "Cloud"),
        ):
            self._routes[key] = _Route(self._pages.addWidget(page), title)

        workspace_layout.addWidget(self._top_bar)
        workspace_layout.addWidget(self._pages, 1)

        shell.addWidget(self._rail)
        shell.addWidget(workspace, 1)
        self.setCentralWidget(root)

        self.modal_host = ModalHost(root)
        root.setProperty("_ntModalHost", self.modal_host)
        self.setProperty("_ntModalHost", self.modal_host)

        self._current = "home"
        self._pages.setCurrentIndex(self._routes["home"].index)
        self._sync_context("Home")

        self._connect()

    # ---------- wiring ----------

    def _connect(self) -> None:
        self._rail.itemActivated.connect(self._on_nav_activated)

        self._top_bar.searchChanged.connect(self._on_search_changed)
        self._top_bar.notificationsRequested.connect(self.open_notifications)
        self._top_bar.profileRequested.connect(self.open_settings)

        self.home.navigateRequested.connect(self.navigate)
        self.home.importRequested.connect(self.import_recording)
        self.home.trainRequested.connect(self.open_training)

        self.projects.primaryActionRequested.connect(self.new_pipeline)
        self.datasets.primaryActionRequested.connect(self.import_recording)
        self.models.primaryActionRequested.connect(self.open_training)
        self.cloud.connectRequested.connect(self.open_cloud_unavailable)

        ProjectDir.instance().root_changed.connect(
            lambda *_: self._sync_context(self._routes[self._current].title)
        )

        search = QShortcut(QKeySequence.StandardKey.Find, self)
        search.activated.connect(self._top_bar.focus_search)

    def _sync_context(self, route_title: str) -> None:
        """Top bar carries the project; the window title carries the view."""
        root = ProjectDir.instance().root
        name = Path(root).name if root else "No project"
        self._top_bar.set_title(name)
        self._top_bar.set_title_tooltip(root or "Choose a project folder in Settings")
        self.setWindowTitle(f"{route_title} — NeuroTendrils")

    # ---------- navigation ----------

    def navigate(self, key: str) -> None:
        route = self._routes.get(key)
        if route is None:
            return
        if key != self._current:
            self._top_bar.clear_search()
        self._current = key
        self._rail.set_current(key)
        self._sync_context(route.title)
        crossfade_stack(self._pages, route.index)

    def _on_nav_activated(self, key: str) -> None:
        if key == "settings":
            self._rail.set_current(self._current)
            self.open_settings()
            return
        self.navigate(key)

    def _on_search_changed(self, text: str) -> None:
        page = self._pages.currentWidget()
        setter = getattr(page, "set_query", None)
        if callable(setter):
            setter(text)

    # ---------- actions ----------

    def new_pipeline(self) -> None:
        self.navigate("flow")
        self.flow.flow.go_to(FLOW_RECORDING)

    def import_recording(self) -> None:
        self.navigate("flow")
        self.flow.import_recording()

    def open_training(self) -> None:
        self.navigate("studio")
        self.studio.flow.go_to(STUDIO_TRAIN)

    def open_notifications(self) -> None:
        modals.alert(
            self,
            "Notifications",
            "You are all caught up. Run failures and sync activity will appear here.",
        )

    def open_cloud_unavailable(self) -> None:
        modals.alert(
            self,
            "Cloud Not Available",
            "Accounts and cloud sync are not enabled in this build. "
            "Everything stays in your local project folder for now.",
        )

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

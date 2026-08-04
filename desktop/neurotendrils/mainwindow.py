from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from neurotendrils.core.library import LibraryBus
from neurotendrils.core.projectdir import ProjectDir
from neurotendrils.core.search import SearchHit, search_index
from neurotendrils.modules.cloud.page import CloudPage
from neurotendrils.modules.home.page import HomePage
from neurotendrils.modules.library.page import LibraryPage
from neurotendrils.modules.neuroflow.page import RECORDING as FLOW_RECORDING
from neurotendrils.modules.neuroflow.page import NeuroFlowPage
from neurotendrils.modules.neurostudio.page import DATA as STUDIO_DATA
from neurotendrils.modules.neurostudio.page import TRAIN as STUDIO_TRAIN
from neurotendrils.modules.neurostudio.page import NeuroStudioPage
from neurotendrils.modules.projects.page import ProjectsPage
from neurotendrils.settingsdialog import SettingsPanel
from neurotendrils.widgets import modals
from neurotendrils.widgets.icons import Glyph
from neurotendrils.widgets.modal_host import ModalHost
from neurotendrils.widgets.motion import crossfade_stack
from neurotendrils.widgets.nav_rail import NavItem, NavRail
from neurotendrils.widgets.notification_panel import NotificationPanel
from neurotendrils.widgets.search_popup import SearchPopup
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
        self._notify_panel: NotificationPanel | None = None
        self._search_popup: SearchPopup | None = None
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._run_search)

        root = QWidget(self)
        root.setObjectName("appRoot")
        self._shell = root
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
        self.projects = ProjectsPage(self._pages)
        self.datasets = LibraryPage(
            "dataset",
            "Datasets",
            "Multi-file lab datasets and recordings in the open project.",
            "Create dataset",
            self._pages,
            secondary_action="Import recording",
        )
        self.models = LibraryPage(
            "model",
            "Models",
            "Models trained and exported from the open project.",
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

        divider = QFrame(root)
        divider.setObjectName("shellDivider")
        divider.setFrameShape(QFrame.Shape.NoFrame)
        divider.setFixedWidth(1)

        shell.addWidget(self._rail)
        shell.addWidget(divider)
        shell.addWidget(workspace, 1)
        self.setCentralWidget(root)

        self.modal_host = ModalHost(root)
        root.setProperty("_ntModalHost", self.modal_host)
        self.setProperty("_ntModalHost", self.modal_host)

        self._current = "home"
        self._pages.setCurrentIndex(self._routes["home"].index)
        search_index().rebuild()
        self._sync_context()

        self._connect()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # ---------- wiring ----------

    def _connect(self) -> None:
        self._rail.itemActivated.connect(self._on_nav_activated)

        self._top_bar.searchChanged.connect(self._on_search_changed)
        self._top_bar.searchSubmitted.connect(self._on_search_submitted)
        self._top_bar.notificationsRequested.connect(self.open_notifications)
        self._top_bar.profileRequested.connect(lambda: self.open_settings("Account"))
        self._top_bar.projectSwitchRequested.connect(self.switch_project)
        self._top_bar.browseFolderRequested.connect(self.browse_project_folder)
        self._top_bar.manageProjectsRequested.connect(lambda: self.navigate("projects"))

        self.home.navigateRequested.connect(self.navigate)
        self.home.importRequested.connect(self.import_recording)
        self.home.trainRequested.connect(self.open_training)

        self.projects.openFlowRequested.connect(self.new_pipeline)
        self.projects.openStudioRequested.connect(self.open_training)
        self.projects.openDatasetRequested.connect(self.open_dataset_in_flow)
        self.projects.openRunRequested.connect(self.open_run_in_studio)
        self.projects.openTemplateRequested.connect(self.open_template_in_studio)
        self.datasets.primaryActionRequested.connect(self.projects.create_lab_dataset)
        self.datasets.secondaryActionRequested.connect(self.projects.import_dataset)
        self.models.primaryActionRequested.connect(self.open_training)
        self.cloud.connectRequested.connect(self.open_cloud_unavailable)

        ProjectDir.instance().root_changed.connect(self._on_project_changed)
        ProjectDir.instance().workspace_changed.connect(lambda *_: self._sync_context())
        LibraryBus.instance().changed.connect(lambda: search_index().rebuild())

        search = QShortcut(QKeySequence.StandardKey.Find, self)
        search.activated.connect(self._top_bar.focus_search)

    def _on_project_changed(self, *_args) -> None:
        search_index().rebuild()
        self._sync_context()

    def _sync_context(self, *_args) -> None:
        self.setWindowTitle("NeuroTendrils")
        self._top_bar.refresh_project()

    # ---------- navigation ----------

    def navigate(self, key: str) -> None:
        route = self._routes.get(key)
        if route is None:
            return
        if key != self._current:
            self._top_bar.clear_search()
            self._hide_popovers()
        self._current = key
        self._rail.set_current(key)
        if key == "projects":
            self.projects.show_grid()
        crossfade_stack(self._pages, route.index)

    def _on_nav_activated(self, key: str) -> None:
        if key == "settings":
            self._rail.set_current(self._current)
            self.open_settings()
            return
        self.navigate(key)

    def switch_project(self, path: str) -> None:
        if not path or path == ProjectDir.instance().root:
            return
        ProjectDir.instance().set_root(path, persist=True, dialog_parent=self)

    def browse_project_folder(self) -> None:
        root = ProjectDir.instance().root
        if root:
            QDesktopServices.openUrl(QUrl.fromLocalFile(root))

    # ---------- search ----------

    def _on_search_changed(self, text: str) -> None:
        page = self._pages.currentWidget()
        setter = getattr(page, "set_query", None)
        if callable(setter):
            setter(text)
        if text.strip():
            self._search_timer.start()
        else:
            self._hide_search_popup()

    def _on_search_submitted(self, text: str) -> None:
        self._search_timer.stop()
        self._run_search(text)

    def _run_search(self, text: str | None = None) -> None:
        query = text if text is not None else self._top_bar.search_text()
        needle = query.strip()
        if not needle:
            self._hide_search_popup()
            return
        hits = search_index().query(needle, limit=48)
        popup = self._ensure_search_popup()
        popup.set_hits(hits, query=needle)
        self._place_search_popup()
        popup.show()
        popup.raise_()

    def _ensure_search_popup(self) -> SearchPopup:
        if self._search_popup is None:
            self._search_popup = SearchPopup(self._shell)
            self._search_popup.hitActivated.connect(self._on_search_hit)
        return self._search_popup

    def _place_search_popup(self) -> None:
        popup = self._ensure_search_popup()
        rect = self._top_bar.search_global_rect()
        local = self._shell.mapFromGlobal(rect.bottomLeft())
        # Slightly wider than the field so titles breathe; clamp to shell.
        width = max(rect.width(), 400)
        width = min(width, max(280, self._shell.width() - local.x() - 16))
        popup.setFixedWidth(width)
        popup.move(local.x(), local.y() + 6)

    def _hide_search_popup(self) -> None:
        if self._search_popup is not None:
            self._search_popup.hide()

    def _on_search_hit(self, hit: SearchHit) -> None:
        self._hide_search_popup()
        self._top_bar.clear_search()
        kind = hit.kind
        if kind == "dataset":
            self.open_dataset_in_flow(hit.path)
        elif kind == "run":
            self.open_run_in_studio(hit.path)
        elif kind == "template":
            self.open_template_in_studio(hit.path)
        elif kind == "model":
            self.navigate("models")
        elif kind == "plan":
            self.navigate("flow")
        elif kind == "project":
            self.navigate("projects")
            self.projects.show_interior()
        else:
            self.navigate(hit.route)

    # ---------- actions ----------

    def new_pipeline(self) -> None:
        self.navigate("flow")
        self.flow.flow.go_to(FLOW_RECORDING)

    def import_recording(self) -> None:
        self.navigate("flow")
        self.flow.import_recording()

    def open_dataset_in_flow(self, path: str) -> None:
        from neurotendrils.core.dataset_manifest import is_dataset_manifest

        # Multi-file manifests are Studio training units; single files go to Flow.
        if is_dataset_manifest(path):
            self.navigate("studio")
            self.studio.set_dataset(path)
            return
        self.navigate("flow")
        self.flow.set_dataset_path(path, False)

    def open_run_in_studio(self, path: str) -> None:
        self.navigate("studio")
        self.studio.set_dataset(path)

    def open_template_in_studio(self, path: str) -> None:
        self.navigate("studio")
        self.studio.apply_saved_template(path)

    def open_training(self) -> None:
        self.navigate("studio")
        self.studio.flow.go_to(
            STUDIO_DATA if not self.studio._dataset_path else STUDIO_TRAIN
        )

    def open_notifications(self) -> None:
        panel = self._ensure_notify_panel()
        if panel.isVisible():
            panel.hide()
            return
        self._hide_search_popup()
        panel.refresh()
        self._place_notify_panel()
        # Defer show past the bell's mouse-release so it doesn't eat the click.
        QTimer.singleShot(0, self._show_notify_panel)

    def _show_notify_panel(self) -> None:
        panel = self._ensure_notify_panel()
        self._place_notify_panel()
        panel.show()
        panel.raise_()

    def _ensure_notify_panel(self) -> NotificationPanel:
        if self._notify_panel is None:
            self._notify_panel = NotificationPanel(self._shell)
        return self._notify_panel

    def _place_notify_panel(self) -> None:
        panel = self._ensure_notify_panel()
        bell = self._top_bar.notify_global_rect()
        local = self._shell.mapFromGlobal(bell.bottomRight())
        panel.adjustSize()
        x = max(8, local.x() - panel.width())
        y = local.y() + 4
        panel.move(x, y)

    def _hide_popovers(self) -> None:
        self._hide_search_popup()
        if self._notify_panel is not None:
            self._notify_panel.hide()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.MouseButtonPress:
            notify_open = self._notify_panel is not None and self._notify_panel.isVisible()
            search_open = self._search_popup is not None and self._search_popup.isVisible()
            if notify_open or search_open:
                mouse = event if isinstance(event, QMouseEvent) else None
                if mouse is not None:
                    self._dismiss_popovers_outside(mouse.globalPosition().toPoint())
        return super().eventFilter(watched, event)

    def _dismiss_popovers_outside(self, global_pos: QPoint) -> None:
        for panel in (self._notify_panel, self._search_popup):
            if panel is None or not panel.isVisible():
                continue
            local = panel.mapFromGlobal(global_pos)
            if not panel.rect().contains(local):
                # Keep open when clicking the controls that own them.
                if panel is self._notify_panel:
                    bell = self._top_bar.notify_global_rect()
                    if bell.contains(global_pos):
                        continue
                if panel is self._search_popup:
                    search = self._top_bar.search_global_rect()
                    if search.contains(global_pos):
                        continue
                panel.hide()

    def open_cloud_unavailable(self) -> None:
        modals.alert(
            self,
            "Cloud Not Available",
            "Accounts and cloud sync are not enabled in this build. "
            "Everything stays in your local project folder for now.",
        )

    def open_settings(self, section: str | None = None) -> None:
        if self._settings is None:
            self._settings = SettingsPanel()
            self._settings.closed.connect(self.modal_host.dismiss)
        if section:
            self._settings.show_section(section)
        self.modal_host.present(
            self._settings,
            dismissible=True,
            own=False,
            max_width=780,
            max_height=560,
        )

from __future__ import annotations

from pathlib import Path

from suite_backend.storage.local import LocalStudyRepository, LocalWorkspace


class AppContext:
    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace = LocalWorkspace(workspace_root)
        self.studies = LocalStudyRepository(self.workspace)

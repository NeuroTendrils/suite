"""Lightweight file index for top-bar search across the active project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from neurotendrils.core.library import LibraryEntry, scan_all
from neurotendrils.core.projectdir import ProjectDir


@dataclass(frozen=True)
class SearchHit:
    kind: str
    title: str
    subtitle: str
    path: str
    route: str  # nav key to open


_ROUTE = {
    "plan": "flow",
    "dataset": "datasets",
    "model": "models",
    "run": "studio",
    "template": "studio",
}


class SearchIndex:
    """Rebuilds from library scans; not a persistent on-disk index."""

    def __init__(self) -> None:
        self._entries: list[LibraryEntry] = []

    def rebuild(self) -> None:
        bags = scan_all()
        entries: list[LibraryEntry] = []
        for key in ("datasets", "plans", "templates", "runs", "models"):
            entries.extend(bags.get(key, []))
        self._entries = entries

    def query(self, text: str, *, limit: int = 48) -> list[SearchHit]:
        needle = text.strip().lower()
        if not needle:
            return []
        if not self._entries:
            self.rebuild()
        # Also match the open project name itself.
        hits: list[SearchHit] = []
        root = ProjectDir.instance().root
        if root and needle in Path(root).name.lower():
            hits.append(
                SearchHit(
                    kind="project",
                    title=Path(root).name,
                    subtitle="Open project",
                    path=root,
                    route="home",
                )
            )
        for entry in self._entries:
            hay = f"{entry.title} {entry.subtitle} {entry.path}".lower()
            if needle not in hay:
                continue
            open_path = entry.path
            if entry.kind == "run":
                open_path = str(entry.extra.get("output_path") or entry.path)
            hits.append(
                SearchHit(
                    kind=entry.kind,
                    title=entry.title,
                    subtitle=entry.subtitle,
                    path=open_path,
                    route=_ROUTE.get(entry.kind, "home"),
                )
            )
            if len(hits) >= limit:
                break
        return hits[:limit]


_INDEX: SearchIndex | None = None


def search_index() -> SearchIndex:
    global _INDEX
    if _INDEX is None:
        _INDEX = SearchIndex()
    return _INDEX

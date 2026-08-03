"""In-app notification center."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from PySide6.QtCore import QObject, Signal

Level = Literal["info", "success", "error"]


@dataclass(frozen=True)
class Notification:
    id: int
    title: str
    body: str
    level: Level
    created_at: float
    read: bool = False


class NotificationCenter(QObject):
    changed = Signal()
    posted = Signal(object)  # Notification

    _instance: NotificationCenter | None = None

    def __init__(self) -> None:
        super().__init__()
        self._items: list[Notification] = []
        self._next_id = 1

    @classmethod
    def instance(cls) -> NotificationCenter:
        if cls._instance is None:
            cls._instance = NotificationCenter()
        return cls._instance

    def items(self) -> list[Notification]:
        return list(self._items)

    def unread_count(self) -> int:
        return sum(1 for item in self._items if not item.read)

    def post(self, title: str, body: str = "", *, level: Level = "info") -> Notification:
        note = Notification(
            id=self._next_id,
            title=title,
            body=body,
            level=level,
            created_at=datetime.now(timezone.utc).timestamp(),
            read=False,
        )
        self._next_id += 1
        self._items.insert(0, note)
        self._items = self._items[:50]
        self.posted.emit(note)
        self.changed.emit()
        return note

    def mark_all_read(self) -> None:
        self._items = [
            Notification(
                id=item.id,
                title=item.title,
                body=item.body,
                level=item.level,
                created_at=item.created_at,
                read=True,
            )
            for item in self._items
        ]
        self.changed.emit()

    def clear(self) -> None:
        self._items.clear()
        self.changed.emit()


def notify(title: str, body: str = "", *, level: Level = "info") -> Notification:
    return NotificationCenter.instance().post(title, body, level=level)

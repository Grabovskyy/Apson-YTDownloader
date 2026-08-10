from __future__ import annotations

from collections.abc import Iterable

from app.core.models import MediaItem, MediaStatus


class QueueManager:
    """Owns queue state without depending on Qt or any GUI widget."""

    def __init__(self) -> None:
        self._items: list[MediaItem] = []

    @property
    def items(self) -> tuple[MediaItem, ...]:
        return tuple(self._items)

    @property
    def selected_items(self) -> tuple[MediaItem, ...]:
        return tuple(item for item in self._items if item.selected)

    def add(self, item: MediaItem) -> None:
        self._items.append(item)

    def add_many(self, items: Iterable[MediaItem]) -> None:
        self._items.extend(items)

    def add_many_unique(self, items: Iterable[MediaItem]) -> int:
        """Add items unless their source id or canonical URL is already queued."""
        known_source_ids = {item.source_id for item in self._items if item.source_id}
        known_urls = {item.url for item in self._items if item.url}
        added = 0

        for item in items:
            duplicate_id = bool(item.source_id and item.source_id in known_source_ids)
            duplicate_url = bool(item.url and item.url in known_urls)
            if duplicate_id or duplicate_url:
                continue
            self._items.append(item)
            if item.source_id:
                known_source_ids.add(item.source_id)
            if item.url:
                known_urls.add(item.url)
            added += 1
        return added

    def get(self, item_id: str) -> MediaItem | None:
        return next((item for item in self._items if item.id == item_id), None)

    def set_selected(self, item_id: str, selected: bool) -> bool:
        item = self.get(item_id)
        if item is None:
            return False
        item.selected = selected
        return True

    def select_all(self) -> None:
        for item in self._items:
            item.selected = True

    def clear_selection(self) -> None:
        for item in self._items:
            item.selected = False

    def remove_selected(self) -> int:
        previous_count = len(self._items)
        self._items = [item for item in self._items if not item.selected]
        return previous_count - len(self._items)

    def update_progress(self, item_id: str, progress: int) -> bool:
        item = self.get(item_id)
        if item is None:
            return False
        item.progress = min(100, max(0, int(progress)))
        if item.progress >= 100:
            item.status = MediaStatus.COMPLETED
        elif item.progress > 0:
            item.status = MediaStatus.DOWNLOADING
        return True

    def set_status(self, item_id: str, status: MediaStatus, progress: int | None = None) -> bool:
        item = self.get(item_id)
        if item is None:
            return False
        item.status = status
        if progress is not None:
            item.progress = min(100, max(0, int(progress)))
        return True

    def clear(self) -> None:
        self._items.clear()

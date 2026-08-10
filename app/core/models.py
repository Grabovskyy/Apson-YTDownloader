from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class MediaStatus(StrEnum):
    READY = "Gotowy"
    QUEUED = "W kolejce"
    DOWNLOADING = "Pobieranie"
    CONVERTING = "Konwersja MP3"
    COMPLETED = "Ukończono"
    PAUSED = "Wstrzymano"
    CANCELLED = "Anulowano"
    ERROR = "Błąd"


@dataclass(slots=True)
class MediaItem:
    url: str
    title: str
    author: str
    duration_seconds: int
    selected: bool = True
    status: MediaStatus = MediaStatus.READY
    progress: int = 0
    id: str = field(default_factory=lambda: uuid4().hex)
    source_id: str | None = None
    thumbnail_url: str | None = None
    playlist_title: str | None = None
    playlist_index: int | None = None

    def __post_init__(self) -> None:
        self.progress = min(100, max(0, int(self.progress)))
        self.duration_seconds = max(0, int(self.duration_seconds))

    @property
    def duration(self) -> str:
        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

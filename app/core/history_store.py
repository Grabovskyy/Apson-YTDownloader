from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.utils.paths import AppPaths

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class HistoryStatus(StrEnum):
    DOWNLOADED = "Pobrano"
    SKIPPED_EXISTING = "Plik już istniał"
    ERROR = "Błąd"
    CANCELLED = "Anulowano"


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    id: str
    finished_at: str
    title: str
    author: str
    source_url: str
    source_id: str | None
    quality: str
    status: HistoryStatus
    output_path: str | None = None
    file_size: int | None = None
    error_message: str | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        author: str,
        source_url: str,
        source_id: str | None,
        quality: str,
        status: HistoryStatus,
        output_path: Path | None = None,
        error_message: str | None = None,
    ) -> "HistoryEntry":
        file_size = None
        if output_path is not None:
            try:
                file_size = output_path.stat().st_size if output_path.is_file() else None
            except OSError:
                file_size = None
        return cls(
            id=uuid4().hex,
            finished_at=datetime.now(UTC).isoformat(timespec="seconds"),
            title=title,
            author=author,
            source_url=source_url,
            source_id=source_id,
            quality=quality,
            status=status,
            output_path=str(output_path) if output_path is not None else None,
            file_size=file_size,
            error_message=error_message,
        )


class HistoryStore:
    """Persist terminal download outcomes in the configured data directory."""

    SCHEMA_VERSION = 1

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self._entries = self._load()

    @property
    def entries(self) -> tuple[HistoryEntry, ...]:
        return tuple(self._entries)

    def add(self, entry: HistoryEntry) -> None:
        self._entries.insert(0, entry)
        self._save()

    def remove(self, entry_ids: set[str]) -> int:
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.id not in entry_ids]
        removed = before - len(self._entries)
        if removed:
            self._save()
        return removed

    def clear(self) -> None:
        if self._entries:
            self._entries.clear()
            self._save()

    def _load(self) -> list[HistoryEntry]:
        target = self.paths.history_file
        if not target.exists():
            return []
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema_version") != self.SCHEMA_VERSION:
                raise ValueError("Nieobsługiwana wersja historii.")
            raw_entries = payload.get("entries")
            if not isinstance(raw_entries, list):
                raise ValueError("Nieprawidłowa lista historii.")
            return [self._entry_from_dict(item) for item in raw_entries if isinstance(item, dict)]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            LOGGER.exception("Nie udało się wczytać historii z %s", target)
            self._preserve_corrupt_file(target)
            return []

    @staticmethod
    def _entry_from_dict(data: dict[str, Any]) -> HistoryEntry:
        return HistoryEntry(
            id=str(data["id"]),
            finished_at=str(data["finished_at"]),
            title=str(data["title"]),
            author=str(data.get("author") or "Nieznany autor"),
            source_url=str(data["source_url"]),
            source_id=str(data["source_id"]) if data.get("source_id") else None,
            quality=str(data.get("quality") or ""),
            status=HistoryStatus(str(data["status"])),
            output_path=str(data["output_path"]) if data.get("output_path") else None,
            file_size=int(data["file_size"]) if data.get("file_size") is not None else None,
            error_message=str(data["error_message"]) if data.get("error_message") else None,
        )

    def _save(self) -> None:
        target = self.paths.history_file
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "entries": [
                {**asdict(entry), "status": entry.status.value}
                for entry in self._entries
            ],
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(target)

    @staticmethod
    def _preserve_corrupt_file(target: Path) -> None:
        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = target.with_name(f"{target.stem}.corrupt-{timestamp}{target.suffix}")
            target.replace(backup)
        except OSError:
            LOGGER.exception("Nie udało się zachować uszkodzonego pliku historii")

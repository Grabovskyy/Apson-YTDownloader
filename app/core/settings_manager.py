from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.utils.paths import AppPaths


class VideoPlaylistBehavior(StrEnum):
    SINGLE_VIDEO = "single_video"
    FULL_PLAYLIST = "full_playlist"


@dataclass(slots=True)
class AppSettings:
    download_folder: str
    audio_quality: str = "320 kbps"
    audio_format: str = "MP3"
    video_playlist_behavior: str = VideoPlaylistBehavior.SINGLE_VIDEO.value
    playlist_item_limit: int = 100
    analysis_timeout_seconds: int = 60


class SettingsManager:
    """Persists user settings as JSON in the configured data location."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths
        self._settings = self._load()

    @property
    def values(self) -> AppSettings:
        return self._settings

    def _defaults(self) -> AppSettings:
        return AppSettings(download_folder=str(self._paths.downloads_dir))

    def _load(self) -> AppSettings:
        defaults = self._defaults()
        path = self._paths.settings_file
        if not path.exists():
            return defaults
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return defaults

        valid_keys = set(asdict(defaults))
        merged = asdict(defaults)
        merged.update({key: value for key, value in raw.items() if key in valid_keys})
        try:
            return self._validated(AppSettings(**merged))
        except (TypeError, ValueError):
            return defaults

    def update(self, **values: object) -> None:
        valid_keys = set(asdict(self._settings))
        candidate = asdict(self._settings)
        for key, value in values.items():
            if key not in valid_keys:
                raise KeyError(f"Nieznane ustawienie: {key}")
            candidate[key] = value
        self._settings = self._validated(AppSettings(**candidate))
        self.save()

    @staticmethod
    def _validated(settings: AppSettings) -> AppSettings:
        settings.download_folder = str(settings.download_folder).strip()
        if not settings.download_folder:
            raise ValueError("Folder pobierania nie może być pusty.")
        if settings.audio_format != "MP3":
            raise ValueError("Obsługiwany jest wyłącznie format MP3.")
        if settings.audio_quality not in {
            "128 kbps",
            "192 kbps",
            "256 kbps",
            "320 kbps",
        }:
            raise ValueError("Nieprawidłowa jakość audio.")
        if settings.video_playlist_behavior not in {
            item.value for item in VideoPlaylistBehavior
        }:
            raise ValueError("Nieprawidłowe zachowanie linku playlisty.")
        settings.playlist_item_limit = int(settings.playlist_item_limit)
        settings.analysis_timeout_seconds = int(settings.analysis_timeout_seconds)
        if not 1 <= settings.playlist_item_limit <= 10_000:
            raise ValueError("Limit playlisty musi mieścić się w zakresie 1–10000.")
        if not 15 <= settings.analysis_timeout_seconds <= 600:
            raise ValueError("Limit czasu analizy musi mieścić się w zakresie 15–600 sekund.")
        return settings

    def save(self) -> None:
        target = self._paths.settings_file
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(self._settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(target)

    @property
    def download_folder(self) -> Path:
        return Path(self._settings.download_folder).expanduser()

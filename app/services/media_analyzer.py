from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.models import MediaItem, MediaStatus
from app.core.settings_manager import VideoPlaylistBehavior
from app.core.toolchain_manager import ToolchainPaths

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class YoutubeDLFactory(Protocol):
    def __call__(self, options: dict[str, Any]) -> Any: ...


class MediaAnalysisError(RuntimeError):
    """An expected extraction failure with a message safe to display in the UI."""

    def __init__(self, url: str, user_message: str) -> None:
        super().__init__(user_message)
        self.url = url
        self.user_message = user_message


class AnalysisSourceKind(StrEnum):
    SINGLE = "single"
    PLAYLIST = "playlist"
    AUTO = "auto"


@dataclass(frozen=True, slots=True)
class AnalysisOptions:
    video_playlist_behavior: str = VideoPlaylistBehavior.SINGLE_VIDEO.value
    playlist_item_limit: int = 100

    def __post_init__(self) -> None:
        if self.video_playlist_behavior not in {
            item.value for item in VideoPlaylistBehavior
        }:
            raise ValueError("Nieprawidłowe zachowanie linku playlisty.")
        if not 1 <= int(self.playlist_item_limit) <= 10_000:
            raise ValueError("Limit playlisty musi mieścić się w zakresie 1–10000.")


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    items: tuple[MediaItem, ...]
    source_kind: AnalysisSourceKind
    requested_url: str
    playlist_title: str | None = None
    reported_entry_count: int | None = None
    truncated: bool = False

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.items)

    def __getitem__(self, index):  # type: ignore[no-untyped-def]
        return self.items[index]


@dataclass(frozen=True, slots=True)
class AnalysisTarget:
    url: str
    kind: AnalysisSourceKind


def analysis_result_to_dict(result: AnalysisResult) -> dict[str, Any]:
    return {
        "items": [
            {
                "url": item.url,
                "title": item.title,
                "author": item.author,
                "duration_seconds": item.duration_seconds,
                "selected": item.selected,
                "status": item.status.value,
                "progress": item.progress,
                "id": item.id,
                "source_id": item.source_id,
                "thumbnail_url": item.thumbnail_url,
                "playlist_title": item.playlist_title,
                "playlist_index": item.playlist_index,
            }
            for item in result.items
        ],
        "source_kind": result.source_kind.value,
        "requested_url": result.requested_url,
        "playlist_title": result.playlist_title,
        "reported_entry_count": result.reported_entry_count,
        "truncated": result.truncated,
    }


def analysis_result_from_dict(data: Mapping[str, Any]) -> AnalysisResult:
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("Brak listy elementów w wyniku analizy.")
    items: list[MediaItem] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        items.append(
            MediaItem(
                url=str(raw.get("url") or ""),
                title=str(raw.get("title") or "Bez tytułu"),
                author=str(raw.get("author") or "Nieznany autor"),
                duration_seconds=int(raw.get("duration_seconds") or 0),
                selected=bool(raw.get("selected", True)),
                status=MediaStatus(str(raw.get("status") or MediaStatus.READY.value)),
                progress=int(raw.get("progress") or 0),
                id=str(raw.get("id") or ""),
                source_id=str(raw["source_id"]) if raw.get("source_id") else None,
                thumbnail_url=(
                    str(raw["thumbnail_url"]) if raw.get("thumbnail_url") else None
                ),
                playlist_title=(
                    str(raw["playlist_title"]) if raw.get("playlist_title") else None
                ),
                playlist_index=(
                    int(raw["playlist_index"]) if raw.get("playlist_index") else None
                ),
            )
        )
    return AnalysisResult(
        items=tuple(items),
        source_kind=AnalysisSourceKind(str(data.get("source_kind") or "single")),
        requested_url=str(data.get("requested_url") or ""),
        playlist_title=(
            str(data["playlist_title"]) if data.get("playlist_title") else None
        ),
        reported_entry_count=(
            int(data["reported_entry_count"])
            if data.get("reported_entry_count") is not None
            else None
        ),
        truncated=bool(data.get("truncated", False)),
    )


class _YtDlpLogger:
    """Route yt-dlp diagnostics into the application's rotating log."""

    def debug(self, message: str) -> None:
        LOGGER.debug("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        LOGGER.info("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        LOGGER.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        LOGGER.error("yt-dlp: %s", message)


class MediaAnalyzer:
    """Extract normalized media metadata without downloading media files."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        ydl_factory: YoutubeDLFactory = YoutubeDL,
        socket_timeout: int = 20,
        toolchain: ToolchainPaths | None = None,
    ) -> None:
        self._cache_dir = (cache_dir or Path.cwd() / "data" / "cache" / "yt-dlp").resolve()
        self._ydl_factory = ydl_factory
        self._socket_timeout = socket_timeout
        self._toolchain = toolchain

    def analyze(
        self,
        urls: list[str] | tuple[str, ...],
        analysis_options: AnalysisOptions | None = None,
    ) -> list[MediaItem]:
        """Analyze several URLs synchronously; callers decide which thread to use."""
        results: list[MediaItem] = []
        for url in urls:
            if url.strip():
                results.extend(self.analyze_url(url.strip(), analysis_options).items)
        return results

    def analyze_url(
        self, url: str, analysis_options: AnalysisOptions | None = None
    ) -> AnalysisResult:
        normalized_url = url.strip()
        if not normalized_url:
            raise MediaAnalysisError(url, "Adres jest pusty.")

        requested_options = analysis_options or AnalysisOptions()
        target = self.classify_url(normalized_url, requested_options)
        is_single = target.kind == AnalysisSourceKind.SINGLE

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {
            "cachedir": str(self._cache_dir),
            "extract_flat": False if is_single else "in_playlist",
            "ignoreerrors": True,
            "logger": _YtDlpLogger(),
            "lazy_playlist": not is_single,
            "noplaylist": is_single,
            "playlistend": None if is_single else requested_options.playlist_item_limit + 1,
            "quiet": True,
            "skip_download": True,
            "socket_timeout": self._socket_timeout,
        }
        if self._toolchain is not None:
            options["ffmpeg_location"] = str(self._toolchain.ffmpeg.parent)
            options["js_runtimes"] = {
                "deno": {"path": str(self._toolchain.deno)}
            }

        try:
            with self._ydl_factory(options) as ydl:
                raw_info = ydl.extract_info(target.url, download=False)
                if raw_info is None:
                    raise MediaAnalysisError(
                        normalized_url,
                        "Materiał jest niedostępny, prywatny albo został usunięty.",
                    )
                info = ydl.sanitize_info(raw_info)
        except MediaAnalysisError:
            raise
        except DownloadError as error:
            LOGGER.exception("yt-dlp nie przeanalizował adresu %s", normalized_url)
            raise MediaAnalysisError(
                normalized_url, self._safe_error_message(str(error))
            ) from error
        except Exception as error:
            LOGGER.exception("Nieoczekiwany błąd analizy adresu %s", normalized_url)
            raise MediaAnalysisError(
                normalized_url, self._safe_error_message(str(error))
            ) from error

        if not isinstance(info, Mapping):
            LOGGER.error("Nieobsługiwany wynik yt-dlp dla %s: %r", normalized_url, type(info))
            raise MediaAnalysisError(normalized_url, "Serwis zwrócił nieprawidłowe metadane.")

        parsed_items = self._parse_result(info, normalized_url)
        items = parsed_items[: requested_options.playlist_item_limit]
        if not items:
            raise MediaAnalysisError(
                normalized_url,
                "Nie znaleziono dostępnych materiałów pod tym adresem.",
            )
        entries = info.get("entries")
        actual_kind = (
            AnalysisSourceKind.PLAYLIST
            if entries is not None
            else AnalysisSourceKind.SINGLE
        )
        reported_count = self._positive_int(
            info.get("playlist_count") or info.get("n_entries")
        )
        truncated = actual_kind == AnalysisSourceKind.PLAYLIST and (
            len(parsed_items) > requested_options.playlist_item_limit
            or bool(reported_count and reported_count > requested_options.playlist_item_limit)
        )
        return AnalysisResult(
            items=tuple(items),
            source_kind=actual_kind,
            requested_url=normalized_url,
            playlist_title=self._text(info.get("title")) if entries is not None else None,
            reported_entry_count=reported_count,
            truncated=truncated,
        )

    @classmethod
    def classify_url(cls, url: str, options: AnalysisOptions) -> AnalysisTarget:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        is_youtube = host in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
            "www.youtu.be",
        }
        if not is_youtube:
            return AnalysisTarget(url, AnalysisSourceKind.AUTO)

        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        path = parsed.path.rstrip("/") or "/"
        explicit_playlist = path == "/playlist" and bool(query.get("list"))
        video_link = (
            host.endswith("youtu.be") and path != "/"
        ) or path in {"/watch"} or path.startswith(("/shorts/", "/live/"))

        if explicit_playlist:
            return AnalysisTarget(url, AnalysisSourceKind.PLAYLIST)
        if video_link:
            if (
                query.get("list")
                and options.video_playlist_behavior
                == VideoPlaylistBehavior.FULL_PLAYLIST.value
            ):
                return AnalysisTarget(url, AnalysisSourceKind.PLAYLIST)
            cleaned_query = [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key not in {"list", "index", "start_radio"}
            ]
            cleaned = urlunsplit(
                (parsed.scheme, parsed.netloc, parsed.path, urlencode(cleaned_query), parsed.fragment)
            )
            return AnalysisTarget(cleaned, AnalysisSourceKind.SINGLE)
        return AnalysisTarget(url, AnalysisSourceKind.AUTO)

    def _parse_result(self, info: Mapping[str, Any], source_url: str) -> list[MediaItem]:
        entries = info.get("entries")
        if entries is None:
            return [self._to_media_item(info, source_url)]

        playlist_title = self._text(info.get("title"))
        results: list[MediaItem] = []
        for fallback_index, entry in enumerate(entries, start=1):
            if not isinstance(entry, Mapping):
                continue
            results.append(
                self._to_media_item(
                    entry,
                    source_url,
                    playlist_title=self._text(entry.get("playlist_title")) or playlist_title,
                    playlist_index=self._positive_int(entry.get("playlist_index")) or fallback_index,
                )
            )
        return results

    def _to_media_item(
        self,
        info: Mapping[str, Any],
        source_url: str,
        *,
        playlist_title: str | None = None,
        playlist_index: int | None = None,
    ) -> MediaItem:
        source_id = self._text(info.get("id"))
        canonical_url = self._canonical_entry_url(
            info,
            source_url,
            source_id,
        )
        author = (
            self._text(info.get("channel"))
            or self._text(info.get("uploader"))
            or "Nieznany autor"
        )
        return MediaItem(
            url=canonical_url,
            title=self._text(info.get("title")) or "Bez tytułu",
            author=author,
            duration_seconds=self._non_negative_int(info.get("duration")),
            source_id=source_id,
            thumbnail_url=self._best_thumbnail(info),
            playlist_title=playlist_title,
            playlist_index=playlist_index,
        )

    @classmethod
    def _canonical_entry_url(
        cls,
        info: Mapping[str, Any],
        source_url: str,
        source_id: str | None,
    ) -> str:
        for key in ("webpage_url", "original_url", "url"):
            candidate = cls._text(info.get(key))
            if candidate and urlsplit(candidate).scheme.lower() in {"http", "https"}:
                return candidate
        source_host = (urlsplit(source_url).hostname or "").lower()
        if source_id and source_host in {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
            "www.youtu.be",
        }:
            return f"https://www.youtube.com/watch?{urlencode({'v': source_id})}"
        return source_url

    @classmethod
    def _best_thumbnail(cls, info: Mapping[str, Any]) -> str | None:
        direct = cls._text(info.get("thumbnail"))
        thumbnails = info.get("thumbnails")
        if not isinstance(thumbnails, list):
            return direct

        candidates = [item for item in thumbnails if isinstance(item, Mapping) and cls._text(item.get("url"))]
        if not candidates:
            return direct

        best = max(
            candidates,
            key=lambda item: (
                cls._non_negative_int(item.get("preference")),
                cls._non_negative_int(item.get("width")) * cls._non_negative_int(item.get("height")),
            ),
        )
        return cls._text(best.get("url")) or direct

    @staticmethod
    def _safe_error_message(raw_message: str) -> str:
        message = raw_message.lower()
        if "timed out" in message or "timeout" in message:
            return "Przekroczono limit czasu połączenia. Spróbuj ponownie."
        if "unsupported url" in message or "no suitable extractor" in message:
            return "Ten adres nie jest obsługiwany przez yt-dlp."
        if "private" in message:
            return "Materiał jest prywatny i nie można odczytać jego metadanych."
        if "unavailable" in message or "removed" in message:
            return "Materiał jest niedostępny albo został usunięty."
        if any(fragment in message for fragment in ("network", "connection", "unable to download")):
            return "Nie udało się połączyć z serwisem. Sprawdź połączenie z internetem."
        return "Nie udało się przeanalizować adresu. Szczegóły zapisano w logu."

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _non_negative_int(value: Any) -> int:
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError, OverflowError):
            return 0

    @classmethod
    def _positive_int(cls, value: Any) -> int | None:
        parsed = cls._non_negative_int(value)
        return parsed if parsed > 0 else None

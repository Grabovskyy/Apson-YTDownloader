from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import Event
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled as YtDownloadCancelled
from yt_dlp.utils import DownloadError, sanitize_filename

from app.core.models import MediaItem
from app.core.toolchain_manager import ToolchainPaths
from app.utils.paths import AppPaths

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class DownloadStage(StrEnum):
    QUEUED = "Oczekiwanie"
    DOWNLOADING = "Pobieranie"
    CONVERTING = "Konwersja MP3"
    COMPLETED = "Ukończono"


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    item_id: str
    source_id: str | None
    source_url: str
    title: str
    output_directory: Path
    audio_format: str
    quality: str


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    item_id: str
    stage: DownloadStage
    percent: float
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    speed_bytes_per_second: float | None = None
    eta_seconds: int | None = None
    filename: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadResult:
    item_id: str
    output_path: Path
    skipped_existing: bool = False


class MediaDownloadError(RuntimeError):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


class MediaDownloadCancelled(RuntimeError):
    pass


class _YtDlpLogger:
    def debug(self, message: str) -> None:
        LOGGER.debug("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        LOGGER.info("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        LOGGER.warning("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        LOGGER.error("yt-dlp: %s", message)


class Downloader:
    """Download and convert one request using bundled tools and yt-dlp."""

    VALID_QUALITIES = {"128 kbps": "128", "192 kbps": "192", "256 kbps": "256", "320 kbps": "320"}

    def __init__(
        self,
        paths: AppPaths,
        toolchain: ToolchainPaths,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = YoutubeDL,
    ) -> None:
        self.paths = paths
        self.toolchain = toolchain
        self._ydl_factory = ydl_factory

    def create_requests(
        self,
        items: tuple[MediaItem, ...],
        output_directory: Path,
        audio_format: str,
        quality: str,
    ) -> tuple[DownloadRequest, ...]:
        if audio_format.upper() != "MP3":
            raise ValueError("W tym etapie obsługiwany jest wyłącznie format MP3.")
        if quality not in self.VALID_QUALITIES:
            raise ValueError(f"Nieobsługiwana jakość audio: {quality}")
        resolved_output = output_directory.expanduser().resolve()
        return tuple(
            DownloadRequest(
                item_id=item.id,
                source_id=item.source_id,
                source_url=item.url,
                title=item.title,
                output_directory=resolved_output,
                audio_format=audio_format.upper(),
                quality=quality,
            )
            for item in items
        )

    def download(
        self,
        request: DownloadRequest,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
        cancel_event: Event | None = None,
    ) -> DownloadResult:
        cancellation = cancel_event or Event()
        if cancellation.is_set():
            raise MediaDownloadCancelled("Pobieranie anulowano.")

        request.output_directory.mkdir(parents=True, exist_ok=True)
        temporary_directory = self.paths.temp_dir / "downloads"
        temporary_directory.mkdir(parents=True, exist_ok=True)
        output_path = request.output_directory / f"{self._output_stem(request)}.mp3"
        if output_path.exists():
            self._emit(
                progress_callback,
                DownloadProgress(
                    item_id=request.item_id,
                    stage=DownloadStage.COMPLETED,
                    percent=100.0,
                    filename=str(output_path),
                ),
            )
            return DownloadResult(request.item_id, output_path, skipped_existing=True)

        def progress_hook(data: dict[str, Any]) -> None:
            self._raise_if_cancelled(cancellation)
            status = data.get("status")
            if status == "downloading":
                downloaded = self._as_int(data.get("downloaded_bytes"))
                total = self._optional_int(data.get("total_bytes")) or self._optional_int(
                    data.get("total_bytes_estimate")
                )
                percent = min(100.0, downloaded * 100.0 / total) if total else 0.0
                self._emit(
                    progress_callback,
                    DownloadProgress(
                        item_id=request.item_id,
                        stage=DownloadStage.DOWNLOADING,
                        percent=percent,
                        downloaded_bytes=downloaded,
                        total_bytes=total,
                        speed_bytes_per_second=self._optional_float(data.get("speed")),
                        eta_seconds=self._optional_int(data.get("eta")),
                        filename=self._text(data.get("filename")),
                    ),
                )
            elif status == "finished":
                self._emit(
                    progress_callback,
                    DownloadProgress(
                        item_id=request.item_id,
                        stage=DownloadStage.CONVERTING,
                        percent=99.0,
                        downloaded_bytes=self._as_int(data.get("downloaded_bytes")),
                        total_bytes=self._optional_int(data.get("total_bytes")),
                        filename=self._text(data.get("filename")),
                    ),
                )

        def postprocessor_hook(data: dict[str, Any]) -> None:
            self._raise_if_cancelled(cancellation)
            status = data.get("status")
            del status
            self._emit(
                progress_callback,
                DownloadProgress(
                    item_id=request.item_id,
                    stage=DownloadStage.CONVERTING,
                    percent=99.0,
                    filename=self._text(data.get("info_dict", {}).get("filepath"))
                    if isinstance(data.get("info_dict"), dict)
                    else None,
                ),
            )

        template = f"{self._output_stem(request).replace('%', '%%')}.%(ext)s"
        options: dict[str, Any] = {
            "cachedir": str(self.paths.cache_dir / "yt-dlp"),
            "continuedl": True,
            "ffmpeg_location": str(self.toolchain.ffmpeg.parent),
            "format": "bestaudio/best",
            "ignoreerrors": False,
            "js_runtimes": {"deno": {"path": str(self.toolchain.deno)}},
            "logger": _YtDlpLogger(),
            "noplaylist": True,
            "nopart": False,
            "outtmpl": {"default": template},
            "overwrites": False,
            "paths": {
                "home": str(request.output_directory),
                "temp": str(temporary_directory),
            },
            "postprocessor_hooks": [postprocessor_hook],
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.VALID_QUALITIES[request.quality],
                }
            ],
            "progress_delta": 0.2,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "socket_timeout": 20,
            "windowsfilenames": True,
            "writethumbnail": False,
        }

        try:
            with self._ydl_factory(options) as ydl:
                info = ydl.extract_info(request.source_url, download=True)
                if info is None:
                    raise MediaDownloadError("Nie udało się pobrać materiału.")
            self._raise_if_cancelled(cancellation)
        except MediaDownloadCancelled:
            raise
        except YtDownloadCancelled as error:
            raise MediaDownloadCancelled("Pobieranie anulowano.") from error
        except DownloadError as error:
            LOGGER.exception("yt-dlp nie pobrał %s", request.source_url)
            raise MediaDownloadError(self._safe_error_message(str(error))) from error
        except MediaDownloadError:
            raise
        except Exception as error:
            LOGGER.exception("Nieoczekiwany błąd pobierania %s", request.source_url)
            raise MediaDownloadError(
                "Wystąpił nieoczekiwany błąd pobierania. Szczegóły zapisano w logu."
            ) from error

        self._emit(
            progress_callback,
            DownloadProgress(
                item_id=request.item_id,
                stage=DownloadStage.COMPLETED,
                percent=100.0,
                filename=str(output_path),
            ),
        )
        return DownloadResult(request.item_id, output_path)

    @staticmethod
    def _output_stem(request: DownloadRequest) -> str:
        identity = request.source_id or request.item_id[:12]
        safe = sanitize_filename(f"{request.title} [{identity}]", is_id=False).rstrip(". ")
        while len(safe.encode("utf-8")) > 180:
            safe = safe[:-1]
        return safe or identity

    @staticmethod
    def _raise_if_cancelled(cancel_event: Event) -> None:
        if cancel_event.is_set():
            raise YtDownloadCancelled("Anulowano przez użytkownika")

    @staticmethod
    def _emit(
        callback: Callable[[DownloadProgress], None] | None,
        progress: DownloadProgress,
    ) -> None:
        if callback is not None:
            callback(progress)

    @staticmethod
    def _safe_error_message(raw_message: str) -> str:
        message = raw_message.lower()
        if "timed out" in message or "timeout" in message:
            return "Przekroczono limit czasu połączenia. Spróbuj ponownie."
        if "private" in message or "sign in" in message:
            return "Materiał wymaga logowania albo jest prywatny."
        if "unavailable" in message or "removed" in message:
            return "Materiał jest niedostępny albo został usunięty."
        if "ffmpeg" in message or "ffprobe" in message:
            return "Konwersja audio nie powiodła się. Sprawdź bundlowany FFmpeg."
        if any(fragment in message for fragment in ("network", "connection", "unable to download")):
            return "Nie udało się połączyć z serwisem. Sprawdź połączenie z internetem."
        return "Nie udało się pobrać materiału. Szczegóły zapisano w logu."

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0

    @classmethod
    def _optional_int(cls, value: Any) -> int | None:
        parsed = cls._as_int(value)
        return parsed if parsed > 0 else None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            parsed = float(value)
            return parsed if parsed >= 0 else None
        except (TypeError, ValueError, OverflowError):
            return None

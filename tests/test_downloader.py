from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from threading import Event
from typing import Any

from yt_dlp.utils import DownloadError

from app.core.models import MediaItem
from app.core.toolchain_manager import ToolchainPaths
from app.services.downloader import (
    DownloadStage,
    Downloader,
    MediaDownloadCancelled,
    MediaDownloadError,
)
from app.utils.paths import AppPaths


class FakeYoutubeDL:
    def __init__(self, options: dict[str, Any], response: Any) -> None:
        self.options = options
        self.response = response

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def extract_info(self, url: str, *, download: bool) -> Any:
        if not download:
            raise AssertionError("Downloader musi używać download=True")
        if isinstance(self.response, Exception):
            raise self.response
        for hook in self.options["progress_hooks"]:
            hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": 50,
                    "total_bytes": 100,
                    "speed": 2048.0,
                    "eta": 7,
                    "filename": "part.webm",
                }
            )
            hook({"status": "finished", "downloaded_bytes": 100, "total_bytes": 100})
        for hook in self.options["postprocessor_hooks"]:
            hook({"status": "started", "info_dict": {}})
            hook({"status": "finished", "info_dict": {}})
        return self.response


class DownloaderTests(unittest.TestCase):
    def _build(self, root: Path, response: Any = None) -> tuple[Downloader, list[dict[str, Any]]]:
        paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=root / "data")
        paths.ensure_directories()
        toolchain = ToolchainPaths(
            root / "tools" / "ffmpeg.exe",
            root / "tools" / "ffprobe.exe",
            root / "tools" / "deno.exe",
        )
        options_seen: list[dict[str, Any]] = []
        payload = response if response is not None else {"id": "source"}

        def factory(options: dict[str, Any]) -> FakeYoutubeDL:
            options_seen.append(options)
            return FakeYoutubeDL(options, payload)

        return Downloader(paths, toolchain, ydl_factory=factory), options_seen

    def _request(self, downloader: Downloader, root: Path):
        item = MediaItem(
            "https://example.test/watch/one",
            "Title: test?",
            "Author",
            20,
            source_id="source-one",
        )
        return downloader.create_requests((item,), root / "output", "MP3", "192 kbps")[0]

    def test_options_progress_and_output_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            downloader, options_seen = self._build(root)
            request = self._request(downloader, root)
            progress = []
            result = downloader.download(request, progress.append)

            options = options_seen[0]
            self.assertEqual(options["format"], "bestaudio/best")
            self.assertEqual(options["postprocessors"][0]["preferredquality"], "192")
            self.assertEqual(options["ffmpeg_location"], str((root / "tools").resolve()))
            self.assertEqual(
                options["js_runtimes"]["deno"]["path"],
                str((root / "tools" / "deno.exe").resolve()),
            )
            self.assertEqual(options["paths"]["temp"], str(downloader.paths.temp_dir / "downloads"))
            self.assertFalse(options["overwrites"])
            self.assertTrue(options["continuedl"])
            self.assertEqual(progress[0].percent, 50.0)
            self.assertEqual(progress[0].speed_bytes_per_second, 2048.0)
            self.assertEqual(progress[0].eta_seconds, 7)
            self.assertEqual(progress[-1].stage, DownloadStage.COMPLETED)
            self.assertEqual(result.output_path.suffix, ".mp3")
            self.assertIn("[source-one]", result.output_path.name)

    def test_existing_file_is_not_downloaded(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            downloader, options_seen = self._build(root)
            request = self._request(downloader, root)
            expected = request.output_directory / f"{downloader._output_stem(request)}.mp3"
            expected.parent.mkdir(parents=True)
            expected.write_bytes(b"existing")

            result = downloader.download(request)

            self.assertTrue(result.skipped_existing)
            self.assertEqual(options_seen, [])
            self.assertEqual(expected.read_bytes(), b"existing")

    def test_pre_cancelled_request_does_not_start_ytdlp(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            downloader, options_seen = self._build(root)
            request = self._request(downloader, root)
            cancellation = Event()
            cancellation.set()
            with self.assertRaises(MediaDownloadCancelled):
                downloader.download(request, cancel_event=cancellation)
            self.assertEqual(options_seen, [])

    def test_cancellation_from_progress_hook_is_mapped(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            downloader, _ = self._build(root)
            request = self._request(downloader, root)
            cancellation = Event()

            def on_progress(value) -> None:
                if value.stage == DownloadStage.DOWNLOADING:
                    cancellation.set()

            with self.assertRaises(MediaDownloadCancelled):
                downloader.download(request, on_progress, cancellation)

    def test_download_error_is_safe(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            downloader, _ = self._build(root, DownloadError("ERROR: Video unavailable"))
            request = self._request(downloader, root)
            with self.assertRaises(MediaDownloadError) as caught:
                downloader.download(request)
            self.assertNotIn("ERROR:", caught.exception.user_message)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.core.models import MediaItem
from app.core.settings_manager import SettingsManager
from app.main_window import MainWindow
from app.services.media_analyzer import MediaAnalysisError
from app.services.downloader import (
    DownloadProgress,
    DownloadRequest,
    DownloadResult,
    DownloadStage,
)
from app.utils.paths import AppPaths


class FakeAnalyzer:
    def analyze_url(self, url: str) -> list[MediaItem]:
        if "bad" in url:
            raise MediaAnalysisError(url, "Nie udało się w teście")
        return [
            MediaItem(
                url,
                "Test title",
                "Test author",
                42,
                source_id=url.rsplit("/", 1)[-1],
            )
        ]


class ImmediateThreadPool:
    def start(self, worker: object) -> None:
        worker.run()  # type: ignore[attr-defined]


class DeferredThreadPool:
    def __init__(self) -> None:
        self.worker: object | None = None

    def start(self, worker: object) -> None:
        self.worker = worker


class FakeDownloader:
    def create_requests(self, items, output_directory, audio_format, quality):
        return tuple(
            DownloadRequest(
                item.id,
                item.source_id,
                item.url,
                item.title,
                output_directory,
                audio_format,
                quality,
            )
            for item in items
        )

    def download(self, request, progress_callback=None, cancel_event=None):
        if progress_callback:
            progress_callback(
                DownloadProgress(request.item_id, DownloadStage.DOWNLOADING, 50.0)
            )
        return DownloadResult(request.item_id, request.output_directory / "result.mp3")


class MainWindowAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(
        self, root: Path, thread_pool: object, downloader: object | None = None
    ) -> MainWindow:
        paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=root / "data")
        paths.ensure_directories()
        return MainWindow(
            paths,
            SettingsManager(paths),
            analyzer=FakeAnalyzer(),  # type: ignore[arg-type]
            downloader=downloader,  # type: ignore[arg-type]
            thread_pool=thread_pool,  # type: ignore[arg-type]
        )

    def test_success_restores_gui_and_adds_item(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            window = self._window(Path(temporary), ImmediateThreadPool())
            window.url_input.setPlainText(
                "https://example.test/good\nhttps://example.test/good\nnot-a-url"
            )
            with patch("app.main_window.QMessageBox.warning") as warning:
                window._analyze_urls()

            self.assertEqual(len(window.queue.items), 1)
            self.assertEqual(window.analyze_button.text(), "Analizuj")
            self.assertTrue(window.url_input.isEnabled())
            self.assertEqual(window.global_progress.maximum(), 100)
            self.assertIn("dodano 1", window.status_label.text())
            warning.assert_called_once()
            window.close()

    def test_error_restores_gui(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            window = self._window(Path(temporary), ImmediateThreadPool())
            window.url_input.setPlainText("https://example.test/bad")
            with patch("app.main_window.QMessageBox.warning") as warning:
                window._analyze_urls()

            self.assertEqual(len(window.queue.items), 0)
            self.assertEqual(window.analyze_button.text(), "Analizuj")
            self.assertTrue(window.url_input.isEnabled())
            warning.assert_called_once()
            window.close()

    def test_cancel_is_cooperative_and_restores_gui(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            pool = DeferredThreadPool()
            window = self._window(Path(temporary), pool)
            window.url_input.setPlainText("https://example.test/good")
            window._analyze_urls()

            self.assertEqual(window.analyze_button.text(), "Anuluj")
            window._analyze_urls()
            self.assertFalse(window.analyze_button.isEnabled())
            self.assertIsNotNone(pool.worker)
            pool.worker.run()  # type: ignore[union-attr]

            self.assertEqual(window.analyze_button.text(), "Analizuj")
            self.assertTrue(window.url_input.isEnabled())
            self.assertIn("anulowana", window.status_label.text())
            window.close()

    def test_download_batch_updates_queue_page_and_progress(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            window = self._window(root, ImmediateThreadPool(), FakeDownloader())
            item = MediaItem(
                "https://example.test/audio",
                "Audio title",
                "Author",
                30,
                source_id="audio-id",
            )
            window.queue.add(item)
            window._refresh_queue()
            window.folder_input.setText(str(root / "output"))

            window._prepare_downloads()

            self.assertEqual(item.status.value, "Ukończono")
            self.assertEqual(item.progress, 100)
            self.assertEqual(window.pages.currentIndex(), 1)
            self.assertEqual(window.global_progress.value(), 100)
            self.assertIn("Ukończono 1", window.download_queue_summary.text())
            self.assertIsNone(window._download_worker)
            self.assertEqual(len(window.history.entries), 1)
            self.assertEqual(window.history.entries[0].status.value, "Pobrano")
            window.close()


if __name__ == "__main__":
    unittest.main()

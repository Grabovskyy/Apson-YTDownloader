from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.models import MediaItem, MediaStatus
from app.core.queue_manager import QueueManager
from app.core.settings_manager import SettingsManager
from app.core.toolchain_manager import ToolchainPaths
from app.services.downloader import Downloader
from app.utils.paths import AppPaths


class QueueManagerTests(unittest.TestCase):
    def test_selection_removal_and_progress(self) -> None:
        first = MediaItem("https://example.test/1", "One", "Author", 65)
        second = MediaItem("https://example.test/2", "Two", "Author", 3661, selected=False)
        queue = QueueManager()
        queue.add_many((first, second))

        self.assertEqual(first.duration, "1:05")
        self.assertEqual(second.duration, "1:01:01")
        self.assertEqual(len(queue.selected_items), 1)
        self.assertTrue(queue.update_progress(first.id, 100))
        self.assertEqual(first.status, MediaStatus.COMPLETED)
        self.assertEqual(queue.remove_selected(), 1)
        self.assertEqual(queue.items, (second,))

    def test_add_many_unique_uses_source_id_and_canonical_url(self) -> None:
        queue = QueueManager()
        first = MediaItem(
            "https://example.test/watch/one", "One", "Author", 10, source_id="one"
        )
        duplicate_id = MediaItem(
            "https://example.test/watch/other", "Duplicate", "Author", 20, source_id="one"
        )
        duplicate_url = MediaItem(
            "https://example.test/watch/one", "Duplicate URL", "Author", 30, source_id="two"
        )
        unique = MediaItem(
            "https://example.test/watch/three", "Three", "Author", 40, source_id="three"
        )

        self.assertEqual(queue.add_many_unique((first, duplicate_id, duplicate_url, unique)), 2)
        self.assertEqual(queue.items, (first, unique))


class ServiceTests(unittest.TestCase):
    def test_request_creation(self) -> None:
        items = (
            MediaItem("https://example.test/watch?v=1", "One", "Author", 120),
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=root / "data")
            toolchain = ToolchainPaths(
                root / "ffmpeg.exe", root / "ffprobe.exe", root / "deno.exe"
            )
            requests = Downloader(paths, toolchain).create_requests(
                items, root / "audio", "MP3", "320 kbps"
            )
            self.assertEqual(requests[0].item_id, items[0].id)
            self.assertEqual(requests[0].quality, "320 kbps")


class PathAndSettingsTests(unittest.TestCase):
    def test_explicit_data_root_and_atomic_settings(self) -> None:
        workspace = Path.cwd()
        with tempfile.TemporaryDirectory(dir=workspace) as temporary:
            root = Path(temporary)
            paths = AppPaths.discover(app_dir=workspace, data_dir=root / "custom-data")
            paths.ensure_directories()
            self.assertEqual(paths.cache_dir, root / "custom-data" / "cache")
            self.assertTrue(paths.logs_dir.is_dir())

            manager = SettingsManager(paths)
            manager.update(audio_quality="192 kbps", download_folder=str(root / "audio"))
            loaded = SettingsManager(paths)
            self.assertEqual(loaded.values.audio_quality, "192 kbps")
            self.assertEqual(loaded.download_folder, root / "audio")

    def test_individual_path_override(self) -> None:
        paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=Path.cwd() / "data")
        custom_logs = Path.cwd() / "custom-logs"
        changed = paths.with_overrides(logs_dir=custom_logs)
        self.assertEqual(changed.logs_dir, custom_logs.resolve())
        self.assertNotEqual(changed.cache_dir, custom_logs.resolve())


if __name__ == "__main__":
    unittest.main()

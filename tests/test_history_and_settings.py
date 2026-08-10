from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.history_store import HistoryEntry, HistoryStatus, HistoryStore
from app.core.settings_manager import SettingsManager, VideoPlaylistBehavior
from app.utils.paths import AppPaths


class HistoryAndSettingsTests(unittest.TestCase):
    def _paths(self, root: Path) -> AppPaths:
        paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=root / "data")
        paths.ensure_directories()
        return paths

    def test_old_settings_are_migrated_with_analysis_defaults(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            paths = self._paths(Path(temporary))
            paths.settings_file.write_text(
                json.dumps(
                    {
                        "download_folder": str(paths.downloads_dir),
                        "audio_quality": "192 kbps",
                        "audio_format": "MP3",
                        "yt_dlp_path": "legacy",
                        "ffmpeg_path": "legacy",
                    }
                ),
                encoding="utf-8",
            )
            settings = SettingsManager(paths).values

        self.assertEqual(settings.audio_quality, "192 kbps")
        self.assertEqual(
            settings.video_playlist_behavior,
            VideoPlaylistBehavior.SINGLE_VIDEO.value,
        )
        self.assertEqual(settings.playlist_item_limit, 100)
        self.assertEqual(settings.analysis_timeout_seconds, 60)

    def test_settings_validate_playlist_limit_and_timeout(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            manager = SettingsManager(self._paths(Path(temporary)))
            with self.assertRaises(ValueError):
                manager.update(playlist_item_limit=0)
            with self.assertRaises(ValueError):
                manager.update(analysis_timeout_seconds=601)
            manager.update(
                playlist_item_limit=10_000,
                analysis_timeout_seconds=15,
                video_playlist_behavior=VideoPlaylistBehavior.FULL_PLAYLIST.value,
            )
            reloaded = SettingsManager(manager._paths).values

        self.assertEqual(reloaded.playlist_item_limit, 10_000)
        self.assertEqual(reloaded.analysis_timeout_seconds, 15)

    def test_history_persists_all_outcomes_and_file_size(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            paths = self._paths(root)
            output = paths.downloads_dir / "audio.mp3"
            output.write_bytes(b"ID3-test")
            store = HistoryStore(paths)
            statuses = tuple(HistoryStatus)
            for status in statuses:
                store.add(
                    HistoryEntry.create(
                        title=status.value,
                        author="Author",
                        source_url="https://example.test/watch",
                        source_id="id",
                        quality="320 kbps",
                        status=status,
                        output_path=output if status == HistoryStatus.DOWNLOADED else None,
                        error_message="Safe error" if status == HistoryStatus.ERROR else None,
                    )
                )

            reloaded = HistoryStore(paths)

        self.assertEqual({entry.status for entry in reloaded.entries}, set(statuses))
        downloaded = next(
            entry for entry in reloaded.entries if entry.status == HistoryStatus.DOWNLOADED
        )
        self.assertEqual(downloaded.file_size, 8)

    def test_corrupt_history_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            paths = self._paths(Path(temporary))
            paths.history_file.write_text("not-json", encoding="utf-8")
            store = HistoryStore(paths)
            backups = list(paths.history_dir.glob("history.corrupt-*.json"))

        self.assertEqual(store.entries, ())
        self.assertEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()

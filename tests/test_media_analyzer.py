from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from yt_dlp.utils import DownloadError

from app.core.settings_manager import VideoPlaylistBehavior
from app.services.media_analyzer import (
    AnalysisOptions,
    AnalysisSourceKind,
    MediaAnalysisError,
    MediaAnalyzer,
)


class FakeYoutubeDL:
    def __init__(self, options: dict[str, Any], responses: dict[str, Any]) -> None:
        self.options = options
        self.responses = responses

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def extract_info(self, url: str, *, download: bool) -> Any:
        if download:
            raise AssertionError("Analiza nie może pobierać materiału")
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    def sanitize_info(self, info: Any) -> Any:
        return info


class MediaAnalyzerTests(unittest.TestCase):
    def _analyzer(
        self, root: Path, responses: dict[str, Any]
    ) -> tuple[MediaAnalyzer, list[dict[str, Any]]]:
        seen_options: list[dict[str, Any]] = []

        def factory(options: dict[str, Any]) -> FakeYoutubeDL:
            seen_options.append(options)
            return FakeYoutubeDL(options, responses)

        return MediaAnalyzer(root / "cache", ydl_factory=factory), seen_options

    def test_single_media_metadata_and_cache_options(self) -> None:
        url = "https://example.test/watch/one"
        response = {
            "id": "source-one",
            "webpage_url": "https://example.test/canonical/one",
            "title": "Example title",
            "channel": "Example channel",
            "duration": 125.9,
            "thumbnails": [
                {"url": "https://img.test/small.jpg", "width": 120, "height": 90},
                {"url": "https://img.test/large.jpg", "width": 1280, "height": 720},
            ],
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            analyzer, options = self._analyzer(root, {url: response})
            items = analyzer.analyze_url(url)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].url, "https://example.test/canonical/one")
            self.assertEqual(items[0].source_id, "source-one")
            self.assertEqual(items[0].author, "Example channel")
            self.assertEqual(items[0].duration_seconds, 125)
            self.assertEqual(items[0].thumbnail_url, "https://img.test/large.jpg")
            self.assertEqual(options[0]["cachedir"], str((root / "cache").resolve()))
            self.assertEqual(options[0]["socket_timeout"], 20)
            self.assertTrue(options[0]["skip_download"])

    def test_playlist_skips_unavailable_entries(self) -> None:
        url = "https://example.test/playlist/list"
        response = {
            "_type": "playlist",
            "title": "My playlist",
            "entries": [
                {
                    "id": "one",
                    "webpage_url": "https://example.test/watch/one",
                    "title": "First",
                    "uploader": "Uploader",
                    "duration": 61,
                    "playlist_index": 4,
                },
                None,
                {
                    "id": "two",
                    "webpage_url": "https://example.test/watch/two",
                    "title": "Second",
                    "duration": None,
                },
            ],
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            analyzer, _ = self._analyzer(Path(temporary), {url: response})
            items = analyzer.analyze_url(url)

        self.assertEqual([item.title for item in items], ["First", "Second"])
        self.assertEqual(items[0].playlist_title, "My playlist")
        self.assertEqual(items[0].playlist_index, 4)
        self.assertEqual(items[1].playlist_index, 3)
        self.assertEqual(items[1].author, "Nieznany autor")
        self.assertEqual(items[1].duration_seconds, 0)

    def test_missing_fields_receive_safe_defaults(self) -> None:
        url = "https://example.test/watch/missing"
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            analyzer, _ = self._analyzer(Path(temporary), {url: {"id": "missing"}})
            item = analyzer.analyze_url(url)[0]

        self.assertEqual(item.url, url)
        self.assertEqual(item.title, "Bez tytułu")
        self.assertEqual(item.author, "Nieznany autor")
        self.assertEqual(item.duration_seconds, 0)

    def test_download_error_is_mapped_to_safe_message(self) -> None:
        url = "https://example.test/unsupported"
        error = DownloadError("ERROR: Unsupported URL")
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            analyzer, _ = self._analyzer(Path(temporary), {url: error})
            with self.assertRaises(MediaAnalysisError) as caught:
                analyzer.analyze_url(url)

        self.assertEqual(caught.exception.url, url)
        self.assertEqual(
            caught.exception.user_message, "Ten adres nie jest obsługiwany przez yt-dlp."
        )

    def test_empty_playlist_is_reported(self) -> None:
        url = "https://example.test/playlist/empty"
        response = {"_type": "playlist", "title": "Empty", "entries": [None]}
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            analyzer, _ = self._analyzer(Path(temporary), {url: response})
            with self.assertRaises(MediaAnalysisError) as caught:
                analyzer.analyze_url(url)

        self.assertIn("Nie znaleziono", caught.exception.user_message)

    def test_youtube_video_with_mix_is_single_by_default(self) -> None:
        original = (
            "https://www.youtube.com/watch?v=NM-Tzbc3h_c"
            "&list=RDdssT6k9iYnw&index=4"
        )
        cleaned = "https://www.youtube.com/watch?v=NM-Tzbc3h_c"
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            analyzer, seen_options = self._analyzer(
                Path(temporary), {cleaned: {"id": "NM-Tzbc3h_c", "title": "One"}}
            )
            result = analyzer.analyze_url(original)

        self.assertEqual(result.source_kind, AnalysisSourceKind.SINGLE)
        self.assertEqual(len(result.items), 1)
        self.assertTrue(seen_options[0]["noplaylist"])
        self.assertFalse(seen_options[0]["extract_flat"])
        self.assertIsNone(seen_options[0]["playlistend"])

    def test_video_can_expand_playlist_with_hard_item_limit(self) -> None:
        url = "https://www.youtube.com/watch?v=one&list=PL-example&index=2"
        response = {
            "_type": "playlist",
            "title": "Limited",
            "playlist_count": 25,
            "entries": [
                {"id": "one", "title": "One"},
                {"id": "two", "title": "Two"},
                {"id": "three", "title": "Three"},
            ],
        }
        options = AnalysisOptions(
            VideoPlaylistBehavior.FULL_PLAYLIST.value, playlist_item_limit=2
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            analyzer, seen_options = self._analyzer(Path(temporary), {url: response})
            result = analyzer.analyze_url(url, options)

        self.assertEqual(result.source_kind, AnalysisSourceKind.PLAYLIST)
        self.assertEqual([item.title for item in result.items], ["One", "Two"])
        self.assertEqual(
            [item.url for item in result.items],
            [
                "https://www.youtube.com/watch?v=one",
                "https://www.youtube.com/watch?v=two",
            ],
        )
        self.assertTrue(result.truncated)
        self.assertEqual(result.reported_entry_count, 25)
        self.assertFalse(seen_options[0]["noplaylist"])
        self.assertEqual(seen_options[0]["extract_flat"], "in_playlist")
        self.assertTrue(seen_options[0]["lazy_playlist"])
        self.assertEqual(seen_options[0]["playlistend"], 3)

    def test_explicit_youtube_playlist_ignores_single_video_default(self) -> None:
        url = "https://www.youtube.com/playlist?list=PL-example"
        target = MediaAnalyzer.classify_url(url, AnalysisOptions())
        self.assertEqual(target.kind, AnalysisSourceKind.PLAYLIST)


if __name__ == "__main__":
    unittest.main()

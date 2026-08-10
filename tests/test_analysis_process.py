from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.services.media_analyzer import AnalysisOptions, AnalysisResult
from app.utils.paths import AppPaths
from app.workers.analysis_process import AnalysisProcessController


class AnalysisProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _paths(self, root: Path) -> AppPaths:
        paths = AppPaths.discover(app_dir=Path.cwd(), data_dir=root / "data")
        paths.ensure_directories()
        return paths

    @staticmethod
    def _success_command() -> tuple[str, tuple[str, ...]]:
        response = {
            "ok": True,
            "result": {
                "items": [
                    {
                        "url": "https://example.test/one",
                        "title": "One",
                        "author": "Author",
                        "duration_seconds": 12,
                        "selected": True,
                        "status": "Gotowy",
                        "progress": 0,
                        "id": "item-one",
                        "source_id": "one",
                        "thumbnail_url": None,
                        "playlist_title": None,
                        "playlist_index": None,
                    }
                ],
                "source_kind": "single",
                "requested_url": "https://example.test/one",
                "playlist_title": None,
                "reported_entry_count": None,
                "truncated": False,
            },
        }
        code = (
            "import sys; sys.stdin.buffer.read(); "
            f"sys.stdout.write({json.dumps(response)!r}); sys.stdout.flush()"
        )
        return sys.executable, ("-c", code)

    @staticmethod
    def _sleep_command() -> tuple[str, tuple[str, ...]]:
        code = "import sys,time; sys.stdin.buffer.read(); time.sleep(30)"
        return sys.executable, ("-c", code)

    def test_successful_process_returns_typed_result(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            controller = AnalysisProcessController(
                ["https://example.test/one"],
                self._paths(Path(temporary)),
                AnalysisOptions(),
                15,
                command=self._success_command(),
            )
            found = QSignalSpy(controller.items_found)
            finished = QSignalSpy(controller.finished)
            controller.start()
            self.assertTrue(finished.wait(5000))

        self.assertEqual(found.count(), 1)
        result = found.at(0)[1]
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.items[0].source_id, "one")
        self.assertEqual(finished.at(0), [False, 1, 0])

    def test_cancel_terminates_active_process(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            controller = AnalysisProcessController(
                ["https://example.test/slow"],
                self._paths(Path(temporary)),
                AnalysisOptions(),
                15,
                command=self._sleep_command(),
            )
            finished = QSignalSpy(controller.finished)
            controller.start()
            QTimer.singleShot(50, controller.cancel)
            self.assertTrue(finished.wait(5000))

        self.assertEqual(finished.at(0), [True, 0, 0])

    def test_timeout_fails_url_and_restores_batch(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            controller = AnalysisProcessController(
                ["https://example.test/slow"],
                self._paths(Path(temporary)),
                AnalysisOptions(),
                15,
                command=self._sleep_command(),
            )
            failed = QSignalSpy(controller.url_failed)
            finished = QSignalSpy(controller.finished)
            controller.start()
            QTimer.singleShot(50, controller._on_timeout)
            self.assertTrue(finished.wait(5000))

        self.assertEqual(failed.count(), 1)
        self.assertIn("limit 15", failed.at(0)[1])
        self.assertEqual(finished.at(0), [False, 0, 1])


if __name__ == "__main__":
    unittest.main()

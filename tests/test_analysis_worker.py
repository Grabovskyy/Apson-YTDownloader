from __future__ import annotations

import unittest

from app.core.models import MediaItem
from app.services.media_analyzer import MediaAnalysisError
from app.workers.analysis_worker import AnalysisWorker


class FakeAnalyzer:
    def analyze_url(self, url: str) -> list[MediaItem]:
        if "bad" in url:
            raise MediaAnalysisError(url, "Testowy bezpieczny błąd")
        if "crash" in url:
            raise RuntimeError("technical test detail")
        return [MediaItem(url, f"Title {url}", "Author", 10, source_id=url)]


class AnalysisWorkerTests(unittest.TestCase):
    def test_partial_success_and_error(self) -> None:
        worker = AnalysisWorker(
            ["https://example.test/good", "https://example.test/bad"], FakeAnalyzer()
        )
        found: list[tuple[str, object]] = []
        errors: list[tuple[str, str]] = []
        finished: list[tuple[bool, int, int]] = []
        worker.signals.items_found.connect(lambda url, items: found.append((url, items)))
        worker.signals.url_failed.connect(lambda url, message: errors.append((url, message)))
        worker.signals.finished.connect(lambda *result: finished.append(result))

        worker.run()

        self.assertEqual(len(found), 1)
        self.assertEqual(errors[0][1], "Testowy bezpieczny błąd")
        self.assertEqual(finished, [(False, 1, 1)])

    def test_cancel_stops_before_next_url_and_preserves_first_result(self) -> None:
        worker = AnalysisWorker(
            ["https://example.test/one", "https://example.test/two"], FakeAnalyzer()
        )
        found: list[str] = []
        finished: list[tuple[bool, int, int]] = []

        def receive(url: str, items: object) -> None:
            del items
            found.append(url)
            worker.cancel()

        worker.signals.items_found.connect(receive)
        worker.signals.finished.connect(lambda *result: finished.append(result))
        worker.run()

        self.assertEqual(found, ["https://example.test/one"])
        self.assertEqual(finished, [(True, 1, 0)])

    def test_unexpected_error_is_contained(self) -> None:
        worker = AnalysisWorker(["https://example.test/crash"], FakeAnalyzer())
        errors: list[str] = []
        finished: list[tuple[bool, int, int]] = []
        worker.signals.url_failed.connect(lambda url, message: errors.append(message))
        worker.signals.finished.connect(lambda *result: finished.append(result))

        worker.run()

        self.assertEqual(len(errors), 1)
        self.assertNotIn("technical test detail", errors[0])
        self.assertEqual(finished, [(False, 0, 1)])


if __name__ == "__main__":
    unittest.main()

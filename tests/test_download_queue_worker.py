from __future__ import annotations

import unittest
from pathlib import Path

from app.services.downloader import (
    DownloadProgress,
    DownloadRequest,
    DownloadResult,
    DownloadStage,
    MediaDownloadCancelled,
    MediaDownloadError,
)
from app.workers.download_queue_worker import DownloadQueueWorker


def request(name: str) -> DownloadRequest:
    return DownloadRequest(
        item_id=name,
        source_id=name,
        source_url=f"https://example.test/{name}",
        title=name,
        output_directory=Path.cwd() / "output",
        audio_format="MP3",
        quality="320 kbps",
    )


class FakeDownloader:
    def download(self, value, progress_callback=None, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise MediaDownloadCancelled()
        if value.item_id == "bad":
            raise MediaDownloadError("Bezpieczny błąd")
        if progress_callback:
            progress_callback(
                DownloadProgress(value.item_id, DownloadStage.DOWNLOADING, 50.0)
            )
        return DownloadResult(value.item_id, value.output_directory / f"{value.item_id}.mp3")


class DownloadQueueWorkerTests(unittest.TestCase):
    def test_error_does_not_stop_next_item(self) -> None:
        worker = DownloadQueueWorker(
            (request("one"), request("bad"), request("three")), FakeDownloader()
        )
        completed: list[str] = []
        errors: list[str] = []
        finished: list[tuple[bool, int, int, int]] = []
        worker.signals.item_completed.connect(lambda item_id, result: completed.append(item_id))
        worker.signals.item_failed.connect(lambda item_id, message: errors.append(item_id))
        worker.signals.queue_finished.connect(lambda *result: finished.append(result))

        worker.run()

        self.assertEqual(completed, ["one", "three"])
        self.assertEqual(errors, ["bad"])
        self.assertEqual(finished, [(False, 2, 1, 0)])

    def test_cancel_current_continues_with_next(self) -> None:
        worker = DownloadQueueWorker((request("one"), request("two")), FakeDownloader())
        cancelled: list[str] = []
        completed: list[str] = []
        first = True

        def on_started(item_id: str) -> None:
            nonlocal first
            if first:
                first = False
                worker.cancel_current()

        worker.signals.item_started.connect(on_started)
        worker.signals.item_cancelled.connect(cancelled.append)
        worker.signals.item_completed.connect(lambda item_id, result: completed.append(item_id))
        worker.run()

        self.assertEqual(cancelled, ["one"])
        self.assertEqual(completed, ["two"])

    def test_cancel_all_marks_remaining_items(self) -> None:
        worker = DownloadQueueWorker(
            (request("one"), request("two"), request("three")), FakeDownloader()
        )
        cancelled: list[str] = []
        finished: list[tuple[bool, int, int, int]] = []
        worker.signals.item_started.connect(lambda item_id: worker.cancel_all())
        worker.signals.item_cancelled.connect(cancelled.append)
        worker.signals.queue_finished.connect(lambda *result: finished.append(result))
        worker.run()

        self.assertEqual(cancelled, ["one", "two", "three"])
        self.assertEqual(finished, [(True, 0, 0, 3)])


if __name__ == "__main__":
    unittest.main()

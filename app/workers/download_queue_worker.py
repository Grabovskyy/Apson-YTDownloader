from __future__ import annotations

import logging
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.services.downloader import (
    DownloadProgress,
    DownloadRequest,
    Downloader,
    MediaDownloadCancelled,
    MediaDownloadError,
)

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class DownloadQueueSignals(QObject):
    queue_started = Signal(int)
    item_started = Signal(str)
    item_progress = Signal(object)
    item_completed = Signal(str, object)
    item_failed = Signal(str, str)
    item_cancelled = Signal(str)
    queue_finished = Signal(bool, int, int, int)


class DownloadQueueWorker(QRunnable):
    """Process an immutable batch sequentially outside the GUI thread."""

    def __init__(self, requests: tuple[DownloadRequest, ...], downloader: Downloader) -> None:
        super().__init__()
        self.requests = requests
        self.downloader = downloader
        self.signals = DownloadQueueSignals()
        self._cancel_current = Event()
        self._stop_all = Event()

    def cancel_current(self) -> None:
        self._cancel_current.set()

    def cancel_all(self) -> None:
        self._stop_all.set()
        self._cancel_current.set()

    @Slot()
    def run(self) -> None:
        completed = 0
        failed = 0
        cancelled = 0
        self.signals.queue_started.emit(len(self.requests))
        try:
            for request in self.requests:
                if self._stop_all.is_set():
                    break
                self._cancel_current.clear()
                self.signals.item_started.emit(request.item_id)
                try:
                    result = self.downloader.download(
                        request,
                        progress_callback=self._emit_progress,
                        cancel_event=self._cancel_current,
                    )
                except MediaDownloadCancelled:
                    cancelled += 1
                    self.signals.item_cancelled.emit(request.item_id)
                    continue
                except MediaDownloadError as error:
                    failed += 1
                    self.signals.item_failed.emit(request.item_id, error.user_message)
                    continue
                except Exception:
                    LOGGER.exception("Nieoczekiwany błąd kolejki dla %s", request.item_id)
                    failed += 1
                    self.signals.item_failed.emit(
                        request.item_id,
                        "Wystąpił nieoczekiwany błąd. Szczegóły zapisano w logu.",
                    )
                    continue
                completed += 1
                self.signals.item_completed.emit(request.item_id, result)
        finally:
            if self._stop_all.is_set():
                started = completed + failed + cancelled
                for request in self.requests[started:]:
                    cancelled += 1
                    self.signals.item_cancelled.emit(request.item_id)
            self.signals.queue_finished.emit(
                self._stop_all.is_set(), completed, failed, cancelled
            )

    def _emit_progress(self, progress: DownloadProgress) -> None:
        self.signals.item_progress.emit(progress)

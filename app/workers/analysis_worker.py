from __future__ import annotations

import logging
from threading import Event

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.services.media_analyzer import (
    AnalysisOptions,
    AnalysisResult,
    AnalysisSourceKind,
    MediaAnalysisError,
    MediaAnalyzer,
)

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class AnalysisWorkerSignals(QObject):
    started = Signal()
    items_found = Signal(str, object)
    url_failed = Signal(str, str)
    status_changed = Signal(str)
    finished = Signal(bool, int, int)


class AnalysisWorker(QRunnable):
    """Analyze URLs sequentially outside the GUI thread with cooperative cancel."""

    def __init__(
        self,
        urls: list[str],
        analyzer: MediaAnalyzer,
        options: AnalysisOptions | None = None,
    ) -> None:
        super().__init__()
        self.urls = tuple(urls)
        self.analyzer = analyzer
        self.options = options or AnalysisOptions()
        self.signals = AnalysisWorkerSignals()
        self._cancel_requested = Event()

    def cancel(self) -> None:
        self._cancel_requested.set()

    @property
    def is_cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()

    @Slot()
    def run(self) -> None:
        successful_urls = 0
        failed_urls = 0
        self.signals.started.emit()

        try:
            total = len(self.urls)
            for index, url in enumerate(self.urls, start=1):
                if self.is_cancel_requested:
                    break
                self.signals.status_changed.emit(
                    f"Analizowanie adresu {index} z {total}: {url}"
                )
                try:
                    try:
                        result = self.analyzer.analyze_url(url, self.options)
                    except TypeError:
                        # Compatibility for injected offline fakes using the old API.
                        result = self.analyzer.analyze_url(url)  # type: ignore[call-arg]
                except MediaAnalysisError as error:
                    if self.is_cancel_requested:
                        break
                    failed_urls += 1
                    self.signals.url_failed.emit(url, error.user_message)
                    continue
                except Exception:
                    LOGGER.exception("Nieoczekiwany błąd workera podczas analizy %s", url)
                    if self.is_cancel_requested:
                        break
                    failed_urls += 1
                    self.signals.url_failed.emit(
                        url,
                        "Wystąpił nieoczekiwany błąd analizy. Szczegóły zapisano w logu.",
                    )
                    continue

                if self.is_cancel_requested:
                    break
                if isinstance(result, list):
                    result = AnalysisResult(
                        items=tuple(result),
                        source_kind=AnalysisSourceKind.AUTO,
                        requested_url=url,
                    )
                successful_urls += 1
                self.signals.items_found.emit(url, result)
        finally:
            self.signals.finished.emit(
                self.is_cancel_requested, successful_urls, failed_urls
            )

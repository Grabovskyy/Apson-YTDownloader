from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict

from PySide6.QtCore import (
    QObject,
    QProcess,
    QProcessEnvironment,
    QTimer,
    Signal,
    Slot,
)

from app.core.toolchain_manager import ToolchainPaths
from app.services.media_analyzer import (
    AnalysisOptions,
    analysis_result_from_dict,
)
from app.utils.paths import AppPaths

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class AnalysisProcessController(QObject):
    """Run each yt-dlp extraction in a disposable, time-bounded process."""

    started = Signal()
    items_found = Signal(str, object)
    url_failed = Signal(str, str)
    status_changed = Signal(str)
    finished = Signal(bool, int, int)

    def __init__(
        self,
        urls: list[str],
        paths: AppPaths,
        options: AnalysisOptions,
        timeout_seconds: int,
        toolchain: ToolchainPaths | None = None,
        parent: QObject | None = None,
        command: tuple[str, tuple[str, ...]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.urls = tuple(urls)
        self.paths = paths
        self.options = options
        self.timeout_seconds = min(600, max(15, int(timeout_seconds)))
        self.toolchain = toolchain
        self._command = command
        self._index = 0
        self._successful = 0
        self._failed = 0
        self._cancelled = False
        self._shutting_down = False
        self._timed_out = False
        self._process: QProcess | None = None
        self._batch_finished = False
        self._stdout = bytearray()
        self._pending_request = b""
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._kill_current)

    @Slot()
    def start(self) -> None:
        self.started.emit()
        self._start_next()

    def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        self._timeout.stop()
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            self._finish_batch()
            return
        process.terminate()
        self._kill_timer.start(2000)

    def shutdown(self) -> None:
        self._shutting_down = True
        self._cancelled = True
        self._timeout.stop()
        self._kill_timer.stop()
        self._kill_current()
        process = self._process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.waitForFinished(2000)

    def _start_next(self) -> None:
        if self._cancelled or self._index >= len(self.urls):
            self._finish_batch()
            return

        url = self.urls[self._index]
        self._timed_out = False
        self._stdout.clear()
        self.status_changed.emit(
            f"Analizowanie adresu {self._index + 1} z {len(self.urls)}: {url}"
        )
        process = QProcess(self)
        self._process = process
        process.setWorkingDirectory(str(self.paths.app_dir))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        process.started.connect(self._send_request)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.finished.connect(self._on_process_finished)
        process.errorOccurred.connect(self._on_process_error)
        process.setProcessEnvironment(self._process_environment())

        if self._command is not None:
            program, configured_arguments = self._command
            arguments = list(configured_arguments)
        elif getattr(sys, "frozen", False):
            program = sys.executable
            arguments = ["--analysis-helper"]
        else:
            program = sys.executable
            arguments = ["-m", "app.workers.analysis_helper"]
        self._pending_request = json.dumps(
            self._request_payload(url), ensure_ascii=False
        ).encode("utf-8")
        process.start(program, arguments)
        self._timeout.start(self.timeout_seconds * 1000)

    @Slot()
    def _send_request(self) -> None:
        process = self._process
        if process is None:
            return
        process.write(self._pending_request)
        process.closeWriteChannel()
        self._pending_request = b""

    def _request_payload(self, url: str) -> dict[str, object]:
        path_names = (
            "app_dir",
            "data_dir",
            "settings_dir",
            "cache_dir",
            "history_dir",
            "thumbnails_dir",
            "temp_dir",
            "logs_dir",
            "downloads_dir",
        )
        toolchain = None
        if self.toolchain is not None:
            toolchain = {
                "ffmpeg": str(self.toolchain.ffmpeg),
                "ffprobe": str(self.toolchain.ffprobe),
                "deno": str(self.toolchain.deno),
            }
        return {
            "url": url,
            "paths": {name: str(getattr(self.paths, name)) for name in path_names},
            "options": asdict(self.options),
            "toolchain": toolchain,
        }

    def _process_environment(self) -> QProcessEnvironment:
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("TEMP", str(self.paths.temp_dir))
        environment.insert("TMP", str(self.paths.temp_dir))
        environment.insert("DENO_DIR", str(self.paths.cache_dir / "deno"))
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUTF8", "1")
        environment.insert("YTDOWNLOADER_DATA_DIR", str(self.paths.data_dir))
        return environment

    @Slot()
    def _read_stdout(self) -> None:
        if self._process is not None:
            self._stdout.extend(bytes(self._process.readAllStandardOutput()))

    @Slot(int, QProcess.ExitStatus)
    def _on_process_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        del exit_code, exit_status
        process = self._process
        if process is None:
            return
        self._read_stdout()
        self._timeout.stop()
        self._kill_timer.stop()
        url = self.urls[self._index]
        if self._cancelled:
            self._dispose_process()
            self._finish_batch()
            return
        if self._timed_out:
            self._record_failure(
                url,
                f"Analiza przekroczyła limit {self.timeout_seconds} sekund i została przerwana.",
            )
        else:
            self._consume_response(url)
        self._dispose_process()
        self._index += 1
        QTimer.singleShot(0, self._start_next)

    def _consume_response(self, url: str) -> None:
        try:
            payload = json.loads(self._stdout.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Nieprawidłowy wynik procesu.")
            if not payload.get("ok"):
                self._record_failure(
                    url, str(payload.get("message") or "Analiza nie powiodła się.")
                )
                return
            result_data = payload.get("result")
            if not isinstance(result_data, dict):
                raise ValueError("Brak wyniku analizy.")
            result = analysis_result_from_dict(result_data)
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            LOGGER.exception("Nieprawidłowa odpowiedź procesu analizy dla %s", url)
            self._record_failure(
                url, "Proces analizy zwrócił nieprawidłowy wynik. Szczegóły zapisano w logu."
            )
            return
        self._successful += 1
        self.items_found.emit(url, result)

    @Slot(QProcess.ProcessError)
    def _on_process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            LOGGER.error("Nie udało się uruchomić procesu analizy")
            if self._process is None or self._cancelled:
                return
            self._timeout.stop()
            self._record_failure(
                self.urls[self._index],
                "Nie udało się uruchomić procesu analizy metadanych.",
            )
            self._dispose_process()
            self._index += 1
            QTimer.singleShot(0, self._start_next)

    @Slot()
    def _on_timeout(self) -> None:
        self._timed_out = True
        process = self._process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            self._kill_timer.start(2000)

    @Slot()
    def _kill_current(self) -> None:
        process = self._process
        if process is not None and process.state() != QProcess.ProcessState.NotRunning:
            process.kill()

    def _record_failure(self, url: str, message: str) -> None:
        self._failed += 1
        self.url_failed.emit(url, message)

    def _dispose_process(self) -> None:
        self._pending_request = b""
        if self._process is not None:
            self._process.deleteLater()
            self._process = None

    def _finish_batch(self) -> None:
        if self._shutting_down or self._batch_finished:
            return
        self._batch_finished = True
        self.finished.emit(self._cancelled, self._successful, self._failed)

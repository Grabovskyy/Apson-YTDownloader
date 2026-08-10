from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
)

from app.core.models import MediaItem
from app.services.downloader import DownloadProgress


class DownloadQueueTable(QTableWidget):
    HEADERS = ("#", "Tytuł", "Status", "Postęp", "Prędkość", "ETA")

    def __init__(self) -> None:
        super().__init__(0, len(self.HEADERS))
        self._rows_by_id: dict[str, int] = {}
        self.setObjectName("QueueTable")
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 48)
        self.setColumnWidth(2, 128)
        self.setColumnWidth(3, 180)
        self.setColumnWidth(4, 112)
        self.setColumnWidth(5, 74)

    def set_items(self, items: tuple[MediaItem, ...]) -> None:
        self.setUpdatesEnabled(False)
        self.setRowCount(len(items))
        self._rows_by_id = {item.id: row for row, item in enumerate(items)}
        for row, item in enumerate(items):
            self.setRowHeight(row, 60)
            self._set_text(row, 0, str(row + 1), Qt.AlignmentFlag.AlignCenter)
            self._set_text(row, 1, item.title)
            self._set_text(row, 2, str(item.status), Qt.AlignmentFlag.AlignCenter)
            progress = QProgressBar()
            progress.setObjectName("ItemProgress")
            progress.setRange(0, 100)
            progress.setValue(item.progress)
            progress.setFormat(f"{item.progress}%")
            self.setCellWidget(row, 3, progress)
            self._set_text(row, 4, "—", Qt.AlignmentFlag.AlignCenter)
            self._set_text(row, 5, "—", Qt.AlignmentFlag.AlignCenter)
        self.setUpdatesEnabled(True)

    def update_item(
        self, item: MediaItem, progress_data: DownloadProgress | None = None
    ) -> None:
        row = self._rows_by_id.get(item.id)
        if row is None:
            return
        status = self.item(row, 2)
        if status is not None:
            status.setText(str(item.status))
        progress = self.cellWidget(row, 3)
        if isinstance(progress, QProgressBar):
            progress.setValue(item.progress)
            progress.setFormat(f"{item.progress}%")
        if progress_data is not None:
            speed = self.item(row, 4)
            eta = self.item(row, 5)
            if speed is not None:
                speed.setText(self._format_speed(progress_data.speed_bytes_per_second))
            if eta is not None:
                eta.setText(self._format_eta(progress_data.eta_seconds))

    def _set_text(
        self,
        row: int,
        column: int,
        value: str,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
    ) -> None:
        cell = QTableWidgetItem(value)
        cell.setTextAlignment(alignment)
        self.setItem(row, column, cell)

    @staticmethod
    def _format_speed(speed: float | None) -> str:
        if speed is None:
            return "—"
        value = speed
        units = ("B/s", "KB/s", "MB/s", "GB/s")
        unit = units[0]
        for candidate in units:
            unit = candidate
            if value < 1024 or candidate == units[-1]:
                break
            value /= 1024
        return f"{value:.1f} {unit}"

    @staticmethod
    def _format_eta(seconds: int | None) -> str:
        if seconds is None:
            return "—"
        minutes, remaining = divmod(max(0, seconds), 60)
        if minutes >= 60:
            hours, minutes = divmod(minutes, 60)
            return f"{hours}:{minutes:02d}:{remaining:02d}"
        return f"{minutes}:{remaining:02d}"

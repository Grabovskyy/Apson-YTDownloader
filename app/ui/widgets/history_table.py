from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from app.core.history_store import HistoryEntry, HistoryStatus


class HistoryTable(QTableWidget):
    HEADERS = ("Data", "Tytuł", "Autor", "Jakość", "Status", "Rozmiar", "Plik")

    def __init__(self) -> None:
        super().__init__(0, len(self.HEADERS))
        self.setObjectName("QueueTable")
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._entries_by_id: dict[str, HistoryEntry] = {}
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

    def set_entries(self, entries: tuple[HistoryEntry, ...]) -> None:
        self.setUpdatesEnabled(False)
        self.setRowCount(len(entries))
        self._entries_by_id = {entry.id: entry for entry in entries}
        for row, entry in enumerate(entries):
            self.setRowHeight(row, 48)
            date_item = self._item(self._formatted_date(entry.finished_at))
            date_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.setItem(row, 0, date_item)
            self.setItem(row, 1, self._item(entry.title, entry.source_url))
            self.setItem(row, 2, self._item(entry.author))
            self.setItem(row, 3, self._item(entry.quality))
            status = self._item(entry.status.value, entry.error_message)
            status.setForeground(self._status_color(entry.status))
            self.setItem(row, 4, status)
            self.setItem(row, 5, self._item(self._formatted_size(entry.file_size)))
            self.setItem(row, 6, self._item(self._file_name(entry.output_path), entry.output_path))
        self.setUpdatesEnabled(True)

    def selected_entry_ids(self) -> set[str]:
        ids: set[str] = set()
        for index in self.selectionModel().selectedRows():
            item = self.item(index.row(), 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole):
                ids.add(str(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def current_entry(self) -> HistoryEntry | None:
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        if item is None:
            return None
        return self._entries_by_id.get(str(item.data(Qt.ItemDataRole.UserRole)))

    @staticmethod
    def _item(text: str, tooltip: str | None = None) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setToolTip(tooltip or text)
        return item

    @staticmethod
    def _formatted_date(value: str) -> str:
        try:
            return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value

    @staticmethod
    def _formatted_size(value: int | None) -> str:
        if value is None:
            return "—"
        size = float(value)
        for suffix in ("B", "KB", "MB", "GB"):
            if size < 1024 or suffix == "GB":
                return f"{size:.0f} {suffix}" if suffix == "B" else f"{size:.1f} {suffix}"
            size /= 1024
        return "—"

    @staticmethod
    def _file_name(value: str | None) -> str:
        return Path(value).name if value else "—"

    @staticmethod
    def _status_color(status: HistoryStatus) -> QColor:
        if status in {HistoryStatus.DOWNLOADED, HistoryStatus.SKIPPED_EXISTING}:
            return QColor("#77d9a8")
        if status == HistoryStatus.ERROR:
            return QColor("#ff788a")
        return QColor("#9ca7ba")

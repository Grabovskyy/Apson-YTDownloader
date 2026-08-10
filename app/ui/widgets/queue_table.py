from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.core.models import MediaItem, MediaStatus


class QueueCheckBox(QCheckBox):
    """Compact checkbox with a crisp tick independent of platform themes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:
        return QSize(20, 20)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#6d9eff" if self.isChecked() else "#3b4658"), 1.2))
        painter.setBrush(QColor("#6d9eff" if self.isChecked() else "#0c121c"))
        painter.drawRoundedRect(1, 1, 18, 18, 5, 5)
        if self.isChecked():
            tick_pen = QPen(QColor("#07111f"), 2.1)
            tick_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(tick_pen)
            painter.drawLine(5, 10, 8, 14)
            painter.drawLine(8, 14, 15, 6)


class QueueTable(QTableWidget):
    HEADERS = ("", "#", "Tytuł", "Kanał / autor", "Długość", "Status")

    def __init__(self, on_selection_changed: Callable[[str, bool], None]) -> None:
        super().__init__(0, len(self.HEADERS))
        self._on_selection_changed = on_selection_changed
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
        self.setMinimumHeight(260)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, 48)
        self.setColumnWidth(1, 48)
        self.setColumnWidth(4, 90)
        self.setColumnWidth(5, 112)

    def set_items(self, items: tuple[MediaItem, ...]) -> None:
        self.setUpdatesEnabled(False)
        self.setRowCount(len(items))
        self._rows_by_id = {item.id: row for row, item in enumerate(items)}
        for row, item in enumerate(items):
            self.setRowHeight(row, 58)
            self._set_checkbox(row, item)
            self._set_text(row, 1, str(row + 1), Qt.AlignmentFlag.AlignCenter)
            self._set_text(row, 2, item.title)
            self._set_text(row, 3, item.author)
            self._set_text(row, 4, item.duration, Qt.AlignmentFlag.AlignCenter)
            status = self._set_text(row, 5, str(item.status), Qt.AlignmentFlag.AlignCenter)
            status.setForeground(self._status_color(item.status))
        self.setUpdatesEnabled(True)

    def update_item(self, item: MediaItem) -> None:
        row = self._rows_by_id.get(item.id)
        if row is None:
            return
        status = self.item(row, 5)
        if status is not None:
            status.setText(str(item.status))
            status.setForeground(self._status_color(item.status))

    def _set_checkbox(self, row: int, item: MediaItem) -> None:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkbox = QueueCheckBox(container)
        checkbox.setChecked(item.selected)
        checkbox.toggled.connect(
            lambda checked, item_id=item.id: self._on_selection_changed(item_id, checked)
        )
        layout.addWidget(checkbox)
        self.setCellWidget(row, 0, container)

    def _set_text(
        self,
        row: int,
        column: int,
        value: str,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
    ) -> QTableWidgetItem:
        cell = QTableWidgetItem(value)
        cell.setTextAlignment(alignment)
        self.setItem(row, column, cell)
        return cell

    @staticmethod
    def _status_color(status: MediaStatus) -> QColor:
        colors = {
            MediaStatus.READY: QColor("#77d9a8"),
            MediaStatus.COMPLETED: QColor("#77d9a8"),
            MediaStatus.ERROR: QColor("#ff788a"),
            MediaStatus.CANCELLED: QColor("#9ca7ba"),
            MediaStatus.PAUSED: QColor("#f0c674"),
        }
        return colors.get(status, QColor("#74a7ff"))

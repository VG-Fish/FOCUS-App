"""Reusable task-list search and filter controls."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QWidget


class TaskFilterBar(QWidget):
    """A compact search/filter bar shared by task-list surfaces."""

    changed = Signal()

    OPTIONS: tuple[tuple[str, str], ...] = (
        ("all", "All open"),
        ("needs_estimate", "Needs estimate"),
        ("ready", "Ready to plan"),
        ("zero_remaining", "Zero remaining"),
        ("deferred", "Deferred"),
        ("due_soon", "Due soon / overdue"),
        ("no_deadline", "No deadline"),
        ("completed", "Completed"),
        ("archived", "Archived"),
    )

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tasks or Areas…")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search tasks")
        self.search.textChanged.connect(self.changed)
        layout.addWidget(self.search, 1)

        self.filter = QComboBox()
        self.filter.setMinimumWidth(190)
        self.filter.setAccessibleName("Task filter")
        self.filter.currentIndexChanged.connect(self.changed)
        layout.addWidget(self.filter)
        self.set_counts({})

    @property
    def query(self) -> str:
        return self.search.text().strip().casefold()

    @property
    def filter_key(self) -> str:
        value = self.filter.currentData()
        return value if isinstance(value, str) else "all"

    def set_counts(self, counts: Mapping[str, int]) -> None:
        """Refresh option counts without changing the user's selection."""

        selected = self.filter_key
        self.filter.blockSignals(True)
        self.filter.clear()
        for key, label in self.OPTIONS:
            count = counts.get(key)
            text = f"{label} ({count})" if count is not None else label
            self.filter.addItem(text, key)
        index = self.filter.findData(selected)
        self.filter.setCurrentIndex(index if index >= 0 else 0)
        self.filter.blockSignals(False)

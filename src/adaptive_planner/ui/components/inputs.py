"""Reusable input components."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QCompleter, QHBoxLayout, QSpinBox, QWidget

from adaptive_planner.platform.timezone import local_timezone_name


class SearchableComboBox(QComboBox):
    """An editable dropdown with case-insensitive contains matching."""

    def __init__(self, parent=None, *, placeholder: str = "Search…") -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(16)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText(placeholder)
        completer = self.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)


class TimezoneComboBox(SearchableComboBox):
    """Searchable IANA timezone picker with an explicit system-local choice."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, placeholder="Search timezones…")
        self.local_name = local_timezone_name()
        self._zones = set(available_timezones()) | {"UTC", self.local_name}
        self.addItem(f"System local — {self.local_name}", self.local_name)
        self.insertSeparator(self.count())
        for name in sorted(self._zones):
            self.addItem(name, name)
        self.setToolTip("Search by city or region. System local follows the timezone configured by macOS.")

    def set_timezone(self, timezone_name: str) -> None:
        if timezone_name == self.local_name:
            self.setCurrentIndex(0)
            return
        index = self.findData(timezone_name)
        self.setCurrentIndex(index if index >= 0 else self.findData("UTC"))

    def timezone_name(self) -> str:
        text = self.currentText().strip()
        if text == f"System local — {self.local_name}":
            return self.local_name
        if text in self._zones:
            return text
        data = self.currentData()
        if isinstance(data, str) and self.itemText(self.currentIndex()) == text:
            return data
        try:
            ZoneInfo(text)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Choose a timezone from the search results.") from exc
        return text


class DurationInput(QWidget):
    """Edit every enabled part of a task duration at the same time.

    A workday is eight hours and a workweek is five workdays. The optional day
    and week fields are controlled by Settings; values are persisted as exact
    integer seconds.
    """

    HOUR_SECONDS = 60 * 60
    DAY_SECONDS = 8 * HOUR_SECONDS
    WEEK_SECONDS = 5 * DAY_SECONDS
    MAX_UNIT_LEVEL = {"Hours": 0, "Days": 1, "Weeks": 2}

    def __init__(self, seconds: int | None, *, max_unit: str = "Hours", parent=None) -> None:
        super().__init__(parent)
        self._max_unit = "Hours"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        self.weeks_input = self._duration_part(" wk", "Weeks (one week is five 8-hour workdays)")
        self.days_input = self._duration_part(" d", "Days (one day is 8 hours)")
        self.hours_input = self._duration_part(" h", "Hours")
        self.minutes_input = self._duration_part(" min", "Minutes", maximum=59)
        self.seconds_input = self._duration_part(" sec", "Seconds", maximum=59)
        for field in (
            self.weeks_input,
            self.days_input,
            self.hours_input,
            self.minutes_input,
            self.seconds_input,
        ):
            layout.addWidget(field, 1)

        self.set_max_unit(max_unit)
        if seconds is not None:
            self.set_seconds(seconds)

    @staticmethod
    def _duration_part(suffix: str, tooltip: str, *, maximum: int = 1_000_000) -> QSpinBox:
        field = QSpinBox()
        field.setRange(0, maximum)
        field.setSuffix(suffix)
        field.setAccelerated(True)
        field.setMinimumWidth(66)
        field.setToolTip(tooltip)
        field.setAccessibleName(tooltip)
        return field

    def set_max_unit(self, max_unit: str) -> None:
        if max_unit not in self.MAX_UNIT_LEVEL:
            raise ValueError(f"Unsupported duration unit: {max_unit}")
        current_seconds = self.seconds
        self._max_unit = max_unit
        level = self.MAX_UNIT_LEVEL[max_unit]
        self.days_input.setVisible(level >= 1)
        self.weeks_input.setVisible(level >= 2)
        self.set_seconds(current_seconds or 0)

    def set_seconds(self, seconds: int) -> None:
        remainder = max(0, int(seconds))
        self.weeks_input.setValue(0)
        self.days_input.setValue(0)
        if self._max_unit == "Weeks":
            weeks, remainder = divmod(remainder, self.WEEK_SECONDS)
            self.weeks_input.setValue(weeks)
        if self._max_unit in {"Days", "Weeks"}:
            days, remainder = divmod(remainder, self.DAY_SECONDS)
            self.days_input.setValue(days)
        hours, remainder = divmod(remainder, self.HOUR_SECONDS)
        minutes, seconds = divmod(remainder, 60)
        self.hours_input.setValue(hours)
        self.minutes_input.setValue(minutes)
        self.seconds_input.setValue(seconds)

    @property
    def seconds(self) -> int | None:
        total = (
            self.hours_input.value() * self.HOUR_SECONDS
            + self.minutes_input.value() * 60
            + self.seconds_input.value()
        )
        if self._max_unit in {"Days", "Weeks"}:
            total += self.days_input.value() * self.DAY_SECONDS
        if self._max_unit == "Weeks":
            total += self.weeks_input.value() * self.WEEK_SECONDS
        if total <= 0:
            return None
        return total


class OptionalMinutesInput(QWidget):
    """An explicit inherited/overridden duration field for planning settings."""

    def __init__(self, value: int | None, parent=None, *, inherited_label: str = "Use global default") -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.override = QCheckBox("Override")
        self.override.setChecked(value is not None)
        self.override.setToolTip(inherited_label)
        self.amount = QSpinBox()
        self.amount.setRange(1, 24 * 60)
        self.amount.setSuffix(" min")
        self.amount.setValue(value or 30)
        self.amount.setEnabled(self.override.isChecked())
        self.override.toggled.connect(self.amount.setEnabled)
        layout.addWidget(self.override)
        layout.addWidget(self.amount, 1)

    @property
    def value(self) -> int | None:
        return self.amount.value() if self.override.isChecked() else None

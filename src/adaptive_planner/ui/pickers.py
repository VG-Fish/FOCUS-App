"""Picker-first date and datetime controls used by planner forms."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class _PickerDialog(QDialog):
    def __init__(
        self,
        selected_date: date,
        parent=None,
        *,
        selected_time: time | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose date and time" if selected_time else "Choose date")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(330)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        self.calendar.setSelectedDate(QDate(selected_date.year, selected_date.month, selected_date.day))
        layout.addWidget(self.calendar)

        self.hour: QComboBox | None = None
        self.minute: QComboBox | None = None
        self.meridiem: QComboBox | None = None
        if selected_time is not None:
            time_row = QHBoxLayout()
            time_row.addWidget(QLabel("Time"))
            self.hour = QComboBox()
            self.hour.addItems([str(value) for value in range(1, 13)])
            self.minute = QComboBox()
            self.minute.addItems([f"{value:02d}" for value in range(60)])
            self.meridiem = QComboBox()
            self.meridiem.addItems(["AM", "PM"])
            hour_12 = selected_time.hour % 12 or 12
            self.hour.setCurrentText(str(hour_12))
            self.minute.setCurrentText(f"{selected_time.minute:02d}")
            self.meridiem.setCurrentText("PM" if selected_time.hour >= 12 else "AM")
            time_row.addWidget(self.hour)
            time_row.addWidget(QLabel(":"))
            time_row.addWidget(self.minute)
            time_row.addWidget(self.meridiem)
            time_row.addStretch()
            layout.addLayout(time_row)

        today = QPushButton("Today")
        today.clicked.connect(lambda: self.calendar.setSelectedDate(QDate.currentDate()))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        apply_button = buttons.addButton("Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        apply_button.setDefault(True)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        button_row = QHBoxLayout()
        button_row.addWidget(today)
        button_row.addStretch()
        button_row.addWidget(buttons)
        layout.addLayout(button_row)

    @property
    def date_value(self) -> date:
        selected = self.calendar.selectedDate()
        return date(selected.year(), selected.month(), selected.day())

    @property
    def time_value(self) -> time:
        assert self.hour is not None and self.minute is not None and self.meridiem is not None
        hour = int(self.hour.currentText()) % 12
        if self.meridiem.currentText() == "PM":
            hour += 12
        return time(hour, int(self.minute.currentText()))


class _TimePickerDialog(QDialog):
    def __init__(self, selected_time: time, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose time")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        row = QHBoxLayout()
        self.hour = QComboBox()
        self.hour.addItems([str(value) for value in range(1, 13)])
        self.minute = QComboBox()
        self.minute.addItems([f"{value:02d}" for value in range(60)])
        self.meridiem = QComboBox()
        self.meridiem.addItems(["AM", "PM"])
        self.hour.setCurrentText(str(selected_time.hour % 12 or 12))
        self.minute.setCurrentText(f"{selected_time.minute:02d}")
        self.meridiem.setCurrentText("PM" if selected_time.hour >= 12 else "AM")
        row.addWidget(self.hour)
        row.addWidget(QLabel(":"))
        row.addWidget(self.minute)
        row.addWidget(self.meridiem)
        layout.addLayout(row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def value(self) -> time:
        hour = int(self.hour.currentText()) % 12
        if self.meridiem.currentText() == "PM":
            hour += 12
        return time(hour, int(self.minute.currentText()))


class DatePickerButton(QPushButton):
    """A non-editable date field that always opens a calendar picker."""

    valueChanged = Signal(object)

    def __init__(self, value: date, parent=None) -> None:
        super().__init__(parent)
        self._value = value
        self.setObjectName("pickerButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._choose)
        self._update_label()

    @property
    def value(self) -> date:
        return self._value

    def set_value(self, value: date) -> None:
        self._value = value
        self._update_label()

    def _choose(self) -> None:
        dialog = _PickerDialog(self._value, self)
        if dialog.exec():
            self.set_value(dialog.date_value)
            self.valueChanged.emit(self._value)

    def _update_label(self) -> None:
        self.setText(f"{self._value.strftime('%a, %b %-d, %Y')}  ▾")


class DateTimePickerButton(QPushButton):
    """A non-editable datetime field with calendar and dropdown time pickers."""

    valueChanged = Signal(object)

    def __init__(self, value: datetime, timezone_name: str, parent=None) -> None:
        super().__init__(parent)
        self.timezone_name = timezone_name
        self.zone = ZoneInfo(timezone_name)
        self._value = value.astimezone(timezone.utc)
        self.setObjectName("pickerButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._choose)
        self._update_label()

    @property
    def value(self) -> datetime:
        return self._value

    def set_value(self, value: datetime) -> None:
        self._value = value.astimezone(timezone.utc)
        self._update_label()

    def _choose(self) -> None:
        local = self._value.astimezone(self.zone)
        dialog = _PickerDialog(local.date(), self, selected_time=local.time().replace(tzinfo=None))
        if dialog.exec():
            chosen = datetime.combine(dialog.date_value, dialog.time_value, tzinfo=self.zone)
            self.set_value(chosen.astimezone(timezone.utc))
            self.valueChanged.emit(self._value)

    def _update_label(self) -> None:
        local = self._value.astimezone(self.zone)
        self.setText(f"{local.strftime('%a, %b %-d, %Y  •  %-I:%M %p')}  ▾")


class TimePickerButton(QPushButton):
    """A non-editable wall-clock time field that opens a compact picker."""

    valueChanged = Signal(object)

    def __init__(self, value: time, parent=None) -> None:
        super().__init__(parent)
        self._value = value.replace(second=0, microsecond=0)
        self.setObjectName("pickerButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._choose)
        self._update_label()

    @property
    def value(self) -> time:
        return self._value

    def set_value(self, value: time) -> None:
        self._value = value.replace(second=0, microsecond=0)
        self._update_label()

    def _choose(self) -> None:
        dialog = _TimePickerDialog(self._value, self)
        if dialog.exec():
            self.set_value(dialog.value)
            self.valueChanged.emit(self._value)

    def _update_label(self) -> None:
        self.setText(f"{self._value.strftime('%-I:%M %p')}  ▾")

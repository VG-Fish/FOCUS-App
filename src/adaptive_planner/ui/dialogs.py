"""Picker-first modal forms for the desktop planner."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from adaptive_planner.domain.types import (
    AreaCreate,
    AreaDTO,
    AreaKind,
    Availability,
    CalendarEventCreate,
    CalendarEventDTO,
    CalendarEventUpdate,
    DeadlineKind,
    PostDuePolicy,
    TaskCreate,
    TimeKind,
)
from adaptive_planner.ui.pickers import DatePickerButton, DateTimePickerButton


def _dialog_buttons(dialog: QDialog, validate: Callable[[], None]) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
    buttons.accepted.connect(validate)
    buttons.rejected.connect(dialog.reject)
    return buttons


def _next_quarter(timezone_name: str) -> datetime:
    current = datetime.now(ZoneInfo(timezone_name)).replace(second=0, microsecond=0)
    return current + timedelta(minutes=15 - current.minute % 15)


class QuickCaptureDialog(QDialog):
    """A compact explicit task form; no capture syntax needs to be memorized."""

    def __init__(
        self,
        areas: tuple[AreaDTO, ...],
        timezone_name: str,
        parent=None,
        *,
        create_area: Callable[[AreaCreate], AreaDTO] | None = None,
    ) -> None:
        super().__init__(parent)
        self.timezone_name = timezone_name
        self.create_area_callback = create_area
        self.area_was_created = False
        self.setWindowTitle("Quick Capture")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        heading = QLabel("Capture a task")
        heading.setObjectName("taskTitle")
        layout.addWidget(heading)
        guidance = QLabel("Add what you know now; only the title is required.")
        guidance.setObjectName("mutedText")
        layout.addWidget(guidance)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.title = QLineEdit()
        self.title.setPlaceholderText("What needs to be done?")
        form.addRow("Title", self.title)

        area_row = QWidget()
        area_layout = QHBoxLayout(area_row)
        area_layout.setContentsMargins(0, 0, 0, 0)
        area_layout.setSpacing(7)
        self.area = QComboBox()
        for area in areas:
            self.area.addItem(area.name, area.id)
        area_layout.addWidget(self.area, 1)
        new_area = QPushButton("New Area…")
        new_area.setEnabled(create_area is not None)
        new_area.clicked.connect(self._create_area)
        area_layout.addWidget(new_area)
        form.addRow("Area", area_row)

        self.estimate = QSpinBox()
        self.estimate.setRange(0, 7 * 24 * 60)
        self.estimate.setSingleStep(15)
        self.estimate.setSpecialValueText("Not estimated")
        self.estimate.setSuffix(" min")
        form.addRow("Estimate", self.estimate)

        self.priority = QComboBox()
        for value, label in (
            (1, "1 · Lowest"),
            (2, "2 · Low"),
            (3, "3 · Normal"),
            (4, "4 · High"),
            (5, "5 · Highest"),
        ):
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(2)
        form.addRow("Priority", self.priority)

        self.deadline_kind = QComboBox()
        self.deadline_kind.addItem("No deadline", DeadlineKind.NONE)
        self.deadline_kind.addItem("Date", DeadlineKind.DATE)
        self.deadline_kind.addItem("Date and time", DeadlineKind.DATETIME)
        form.addRow("Deadline", self.deadline_kind)
        self.deadline_stack = QStackedWidget()
        no_deadline = QLabel("No deadline")
        no_deadline.setObjectName("mutedText")
        self.deadline_stack.addWidget(no_deadline)
        self.due_date = DatePickerButton(datetime.now(ZoneInfo(timezone_name)).date())
        self.deadline_stack.addWidget(self.due_date)
        self.due_at = DateTimePickerButton(_next_quarter(timezone_name), timezone_name)
        self.deadline_stack.addWidget(self.due_at)
        self.deadline_kind.currentIndexChanged.connect(self.deadline_stack.setCurrentIndex)
        form.addRow("", self.deadline_stack)

        self.description = QTextEdit()
        self.description.setPlaceholderText("Optional context")
        self.description.setMaximumHeight(82)
        form.addRow("Description", self.description)
        layout.addLayout(form)

        layout.addWidget(_dialog_buttons(self, self._validate))
        for sequence in ("Meta+Return", "Ctrl+Return"):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(self._validate)
        self.title.setFocus()

    def _create_area(self) -> None:
        if self.create_area_callback is None:
            return
        dialog = AreaDialog(self)
        if not dialog.exec():
            return
        try:
            area = self.create_area_callback(dialog.value)
        except Exception as exc:
            QMessageBox.warning(self, "Could not create Area", str(exc))
            return
        self.area.addItem(area.name, area.id)
        self.area.setCurrentIndex(self.area.count() - 1)
        self.area_was_created = True

    def _validate(self) -> None:
        if not self.title.text().strip():
            QMessageBox.warning(self, "Task needs a title", "Enter a short title before saving.")
            return
        self.accept()

    @property
    def value(self) -> TaskCreate:
        kind = DeadlineKind(self.deadline_kind.currentData())
        return TaskCreate(
            area_id=self.area.currentData(),
            title=self.title.text(),
            description=self.description.toPlainText().strip() or None,
            deadline_kind=kind,
            due_date=self.due_date.value if kind is DeadlineKind.DATE else None,
            due_at=self.due_at.value if kind is DeadlineKind.DATETIME else None,
            estimated_remaining_minutes=self.estimate.value() or None,
            priority=self.priority.currentData(),
        )


class AreaDialog(QDialog):
    def __init__(self, parent=None, *, title: str = "New Area", initial_name: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        form = QFormLayout(self)
        self.name = QLineEdit(initial_name)
        self.name.selectAll()
        form.addRow("Name", self.name)

        self.kind = QComboBox()
        for kind in AreaKind:
            self.kind.addItem(kind.value.title(), kind)
        form.addRow("Kind", self.kind)
        self.post_due_policy = QComboBox()
        self.post_due_policy.addItem("Ask me", PostDuePolicy.ASK)
        self.post_due_policy.addItem("Allow work after due date", PostDuePolicy.ALLOW)
        self.post_due_policy.addItem("Never schedule after due date", PostDuePolicy.FORBID)
        form.addRow("After due date", self.post_due_policy)
        if initial_name:
            self.kind.hide()
            self.post_due_policy.hide()
            form.labelForField(self.kind).hide()
            form.labelForField(self.post_due_policy).hide()
        form.addRow(_dialog_buttons(self, self._validate))
        self.name.setFocus()

    def _validate(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Area needs a name", "Give this Area a name before saving.")
            return
        self.accept()

    @property
    def value(self) -> AreaCreate:
        return AreaCreate(
            name=self.name.text(),
            kind=AreaKind(self.kind.currentData()),
            default_post_due_policy=PostDuePolicy(self.post_due_policy.currentData()),
        )


class BlockTimeDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        initial_start: datetime | None = None,
        initial_end: datetime | None = None,
        timezone_name: str = "UTC",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Block Time")
        self.setMinimumWidth(470)
        start = initial_start or _next_quarter(timezone_name)
        end = initial_end or start + timedelta(hours=1)
        form = QFormLayout(self)
        self.title = QLineEdit("Protected time")
        self.start = DateTimePickerButton(start, timezone_name)
        self.end = DateTimePickerButton(end, timezone_name)
        form.addRow("Title", self.title)
        form.addRow("Starts", self.start)
        form.addRow("Ends", self.end)
        form.addRow(_dialog_buttons(self, self._validate))
        self.title.selectAll()
        self.title.setFocus()

    def _validate(self) -> None:
        if not self.title.text().strip():
            QMessageBox.warning(self, "Block needs a title", "Give this protected time a title.")
            return
        if self.end.value <= self.start.value:
            QMessageBox.warning(self, "Invalid time range", "The end must be after the start.")
            return
        self.accept()

    @property
    def values(self) -> tuple[str, datetime, datetime]:
        return self.title.text().strip(), self.start.value, self.end.value


class EventDialog(QDialog):
    """Edit all user-facing attributes of an existing CalendarEvent."""

    def __init__(
        self,
        event: CalendarEventDTO,
        areas: tuple[AreaDTO, ...],
        timezone_name: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.timezone_name = timezone_name
        self.setWindowTitle("Edit Calendar Event")
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        form.setVerticalSpacing(10)

        self.title = QLineEdit(event.title)
        form.addRow("Title", self.title)
        self.description = QTextEdit(event.description or "")
        self.description.setMaximumHeight(80)
        form.addRow("Description", self.description)
        self.area = QComboBox()
        self.area.addItem("None", None)
        for area in areas:
            self.area.addItem(area.name, area.id)
            if area.id == event.area_id:
                self.area.setCurrentIndex(self.area.count() - 1)
        form.addRow("Area", self.area)
        self.availability = QComboBox()
        self.availability.addItem("Busy · consumes time", Availability.BUSY)
        self.availability.addItem("Free · display only", Availability.FREE)
        self.availability.setCurrentIndex(0 if event.availability is Availability.BUSY else 1)
        form.addRow("Availability", self.availability)
        self.time_kind = QComboBox()
        self.time_kind.addItem("Timed", TimeKind.TIMED)
        self.time_kind.addItem("All day", TimeKind.ALL_DAY)
        self.time_kind.setCurrentIndex(0 if event.time_kind is TimeKind.TIMED else 1)
        form.addRow("When", self.time_kind)

        zone = ZoneInfo(timezone_name)
        start = event.start_at or datetime.combine(event.start_date or date.today(), time(hour=9), tzinfo=zone)
        end = event.end_at or start + timedelta(hours=1)
        self.time_stack = QStackedWidget()
        timed_page = QWidget()
        timed_form = QFormLayout(timed_page)
        timed_form.setContentsMargins(0, 0, 0, 0)
        self.start = DateTimePickerButton(start, timezone_name)
        self.end = DateTimePickerButton(end, timezone_name)
        timed_form.addRow("Starts", self.start)
        timed_form.addRow("Ends", self.end)
        self.time_stack.addWidget(timed_page)

        all_day_page = QWidget()
        all_day_form = QFormLayout(all_day_page)
        all_day_form.setContentsMargins(0, 0, 0, 0)
        first_day = event.start_date or start.astimezone(zone).date()
        last_day = event.end_date - timedelta(days=1) if event.end_date else first_day
        self.start_date = DatePickerButton(first_day)
        self.last_date = DatePickerButton(last_day)
        all_day_form.addRow("Starts", self.start_date)
        all_day_form.addRow("Last day", self.last_date)
        self.time_stack.addWidget(all_day_page)
        self.time_stack.setCurrentIndex(self.time_kind.currentIndex())
        self.time_kind.currentIndexChanged.connect(self.time_stack.setCurrentIndex)
        form.addRow("", self.time_stack)
        form.addRow(_dialog_buttons(self, self._validate))
        self.title.setFocus()

    def _validate(self) -> None:
        if not self.title.text().strip():
            QMessageBox.warning(self, "Event needs a title", "Enter a title before saving.")
            return
        try:
            CalendarEventCreate.model_validate(self.value.model_dump(exclude_unset=True))
        except ValueError as exc:
            QMessageBox.warning(self, "Event needs attention", str(exc))
            return
        self.accept()

    @property
    def value(self) -> CalendarEventUpdate:
        kind = TimeKind(self.time_kind.currentData())
        timed = kind is TimeKind.TIMED
        return CalendarEventUpdate(
            title=self.title.text(),
            description=self.description.toPlainText().strip() or None,
            area_id=self.area.currentData(),
            availability=Availability(self.availability.currentData()),
            time_kind=kind,
            start_at=self.start.value if timed else None,
            end_at=self.end.value if timed else None,
            start_date=None if timed else self.start_date.value,
            end_date=None if timed else self.last_date.value + timedelta(days=1),
            timezone_name=self.timezone_name,
        )


class EstimateDialog(QDialog):
    def __init__(self, current: int | None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Remaining work")
        self.setMinimumWidth(340)
        form = QFormLayout(self)
        self.minutes = QSpinBox()
        self.minutes.setRange(0, 7 * 24 * 60)
        self.minutes.setValue(current or 0)
        self.minutes.setSuffix(" min")
        form.addRow("Remaining", self.minutes)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @property
    def value(self) -> int:
        return self.minutes.value()


class HelpDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adaptive Planner Help")
        self.resize(600, 540)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(
            """
            <h2>Adaptive Planner v0.1</h2>
            <p>A local-first task and calendar planner. Your data stays in the local SQLite database.</p>
            <h3>Current capabilities</h3>
            <ul>
              <li>Capture tasks with an Area, estimate, priority, description, and optional deadline.</li>
              <li>Review open tasks and update remaining work, defer, or complete them.</li>
              <li>Create, inspect, edit, and cancel events in day, week, and month views.</li>
              <li>Create Areas, review change History, and inspect DTOs in Debug mode.</li>
              <li>Configure defaults that later scheduler versions will use.</li>
            </ul>
            <h3>Calendar tips</h3>
            <ul>
              <li>Double-click empty calendar space to create a block there.</li>
              <li>Double-click an event, or select it and choose <b>Edit selected</b>, to change it.</li>
              <li>The all-day editor uses an inclusive “Last day” field.</li>
            </ul>
            <h3>Keyboard shortcuts</h3>
            <table cellspacing="7">
              <tr><td><b>⌘⇧Space</b></td><td>Quick Capture</td></tr>
              <tr><td><b>⌘⇧H</b></td><td>Open this help</td></tr>
              <tr><td><b>⌘⇧S</b></td><td>Open Settings</td></tr>
              <tr><td><b>⌘⇧D</b></td><td>Toggle Debug Inspector</td></tr>
              <tr><td><b>⌘Return</b></td><td>Save Quick Capture</td></tr>
            </table>
            """
        )
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

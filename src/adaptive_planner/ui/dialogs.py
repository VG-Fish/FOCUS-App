"""Picker-first modal forms for the desktop planner."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
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
    TaskDTO,
    TaskUpdate,
    TimeKind,
)
from adaptive_planner.ui.components import DurationInput, OptionalMinutesInput
from adaptive_planner.ui.pickers import DatePickerButton, DateTimePickerButton


def _dialog_buttons(dialog: QDialog, validate: Callable[[], None]) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
    # Enter is intentionally not a save gesture in data-entry dialogs. Saving
    # requires an explicit click until we have a more deliberate submit UX.
    for button in buttons.buttons():
        if isinstance(button, QPushButton):
            button.setAutoDefault(False)
            button.setDefault(False)
    buttons.accepted.connect(validate)
    buttons.rejected.connect(dialog.reject)
    return buttons


def _next_quarter(timezone_name: str) -> datetime:
    current = datetime.now(ZoneInfo(timezone_name)).replace(second=0, microsecond=0)
    return current + timedelta(minutes=15 - current.minute % 15)


class _ManualSaveDialog(QDialog):
    """A form dialog where Return can never stand in for clicking Save."""

    _enter_keys = (Qt.Key.Key_Return, Qt.Key.Key_Enter)

    def event(self, event: QEvent) -> bool:
        # Claim the shortcut override before Qt can route Return to a dialog's
        # accept-role/default button. The focused editor still receives its
        # normal key press (for example, a newline in QTextEdit).
        if (
            event.type() is QEvent.Type.ShortcutOverride
            and isinstance(event, QKeyEvent)
            and event.key() in self._enter_keys
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # QLineEdit and other single-line controls may pass Return up to the
        # dialog. Consume it instead of allowing QDialog to accept the form.
        if event.key() in self._enter_keys:
            event.accept()
            return
        super().keyPressEvent(event)


class QuickCaptureDialog(_ManualSaveDialog):
    """A compact explicit task form; no capture syntax needs to be memorized."""

    def __init__(
        self,
        areas: tuple[AreaDTO, ...],
        timezone_name: str,
        parent=None,
        *,
        create_area: Callable[[AreaCreate], AreaDTO] | None = None,
        max_estimate_unit: str = "Hours",
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

        self.estimate = DurationInput(None, max_unit=max_estimate_unit)
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
            estimated_remaining_seconds=self.estimate.seconds,
            priority=self.priority.currentData(),
        )


class AreaDialog(_ManualSaveDialog):
    def __init__(self, parent=None, *, title: str = "New Area", initial_name: str = "", initial_kind: AreaKind = AreaKind.OTHER, initial_policy: PostDuePolicy = PostDuePolicy.ASK) -> None:
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
            if kind is initial_kind:
                self.kind.setCurrentIndex(self.kind.count() - 1)
        form.addRow("Kind", self.kind)
        self.post_due_policy = QComboBox()
        self.post_due_policy.addItem("Ask me", PostDuePolicy.ASK)
        self.post_due_policy.addItem("Allow work after due date", PostDuePolicy.ALLOW)
        self.post_due_policy.addItem("Never schedule after due date", PostDuePolicy.FORBID)
        self.post_due_policy.setCurrentIndex(list(PostDuePolicy).index(initial_policy))
        form.addRow("After due date", self.post_due_policy)
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


class ArchiveAreaDialog(_ManualSaveDialog):
    """Choose explicitly what happens to incomplete Tasks during archival."""

    def __init__(self, area: AreaDTO, task_count: int, destinations: tuple[AreaDTO, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Archive Area")
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"{area.name} contains {task_count} incomplete task(s). "
            "Choose what should happen to them."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        form = QFormLayout()
        self.action = QComboBox()
        self.action.addItem("Archive the Area and its tasks", "archive_contents")
        self.action.addItem("Move tasks to another Area", "move_contents")
        form.addRow("Tasks", self.action)
        self.destination = QComboBox()
        for destination in destinations:
            self.destination.addItem(destination.name, destination.id)
        form.addRow("Destination", self.destination)
        layout.addLayout(form)
        layout.addWidget(_dialog_buttons(self, self._validate))
        self.action.currentIndexChanged.connect(self._update_destination)
        self._update_destination()

    def _update_destination(self) -> None:
        self.destination.setEnabled(self.action.currentData() == "move_contents")

    def _validate(self) -> None:
        if self.action.currentData() == "move_contents" and self.destination.currentData() is None:
            QMessageBox.warning(self, "Choose an Area", "Choose where the incomplete tasks should move.")
            return
        self.accept()

    @property
    def value(self) -> tuple[str, UUID | None]:
        action = str(self.action.currentData())
        destination = self.destination.currentData() if action == "move_contents" else None
        return action, destination


class DeferTaskDialog(_ManualSaveDialog):
    """Fast local-time presets plus a picker for Task earliest-start time."""

    def __init__(
        self,
        timezone_name: str,
        current_value: datetime | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.timezone_name = timezone_name
        self.zone = ZoneInfo(timezone_name)
        self.setWindowTitle("Defer Task")
        self.setMinimumWidth(470)
        now = datetime.now(self.zone).replace(second=0, microsecond=0)
        tonight = datetime.combine(now.date(), time(hour=18), tzinfo=self.zone)
        if tonight <= now:
            tonight = (now + timedelta(hours=2)).replace(
                minute=((now.minute + 14) // 15 * 15) % 60
            )
            if tonight <= now:
                tonight += timedelta(minutes=15)
        tomorrow = datetime.combine(now.date() + timedelta(days=1), time(hour=9), tzinfo=self.zone)
        days_until_monday = (7 - now.weekday()) % 7 or 7
        monday = datetime.combine(
            now.date() + timedelta(days=days_until_monday),
            time(hour=9),
            tzinfo=self.zone,
        )

        form = QFormLayout(self)
        self.choice = QComboBox()
        self.choice.addItem(f"Tonight · {tonight.strftime('%-I:%M %p')}", tonight)
        self.choice.addItem(f"Tomorrow · {tomorrow.strftime('%-I:%M %p')}", tomorrow)
        self.choice.addItem(f"Monday · {monday.strftime('%b %-d at %-I:%M %p')}", monday)
        self.choice.addItem("Choose date and time…", "custom")
        if current_value is not None:
            self.choice.addItem("Remove defer", None)
        form.addRow("Until", self.choice)
        initial = current_value or tomorrow
        self.custom = DateTimePickerButton(initial, timezone_name)
        self.custom.hide()
        form.addRow("Custom", self.custom)
        self.choice.currentIndexChanged.connect(
            lambda _index: self.custom.setVisible(self.choice.currentData() == "custom")
        )
        form.addRow(_dialog_buttons(self, self.accept))

    @property
    def value(self) -> datetime | None:
        selected = self.choice.currentData()
        if selected == "custom":
            return self.custom.value
        if isinstance(selected, datetime):
            return selected.astimezone(ZoneInfo("UTC"))
        return None


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


class EstimateDialog(_ManualSaveDialog):
    def __init__(self, current_seconds: int | None, parent=None, *, max_unit: str = "Hours") -> None:
        super().__init__(parent)
        self.setWindowTitle("Remaining work")
        self.setMinimumWidth(340)
        form = QFormLayout(self)
        self.estimate = DurationInput(current_seconds, max_unit=max_unit)
        form.addRow("Remaining", self.estimate)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        for button in buttons.buttons():
            if isinstance(button, QPushButton):
                button.setAutoDefault(False)
                button.setDefault(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    @property
    def value(self) -> int:
        return self.estimate.seconds or 0


class TaskDialog(_ManualSaveDialog):
    """Edit task attributes beyond its remaining estimate."""

    def __init__(self, task: TaskDTO, areas: tuple[AreaDTO, ...], timezone_name: str, parent=None, *, max_unit: str = "Hours") -> None:
        super().__init__(parent)
        self.task = task
        self.timezone_name = timezone_name
        self.setWindowTitle("Edit Task")
        self.setMinimumWidth(540)
        form = QFormLayout(self)
        self.title = QLineEdit(task.title)
        form.addRow("Title", self.title)
        self.area = QComboBox()
        for area in areas:
            self.area.addItem(area.name, area.id)
            if area.id == task.area_id:
                self.area.setCurrentIndex(self.area.count() - 1)
        form.addRow("Area", self.area)
        self.estimate = DurationInput(task.estimated_remaining_seconds, max_unit=max_unit)
        form.addRow("Estimate", self.estimate)
        self.priority = QComboBox()
        for value, label in ((1, "1 · Lowest"), (2, "2 · Low"), (3, "3 · Normal"), (4, "4 · High"), (5, "5 · Highest")):
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(task.priority - 1)
        form.addRow("Priority", self.priority)
        self.deadline_kind = QComboBox()
        for kind, label in ((DeadlineKind.NONE, "No deadline"), (DeadlineKind.DATE, "Date"), (DeadlineKind.DATETIME, "Date and time")):
            self.deadline_kind.addItem(label, kind)
        self.deadline_kind.setCurrentIndex(list(DeadlineKind).index(task.deadline_kind))
        form.addRow("Deadline", self.deadline_kind)
        self.deadline_stack = QStackedWidget()
        self.deadline_stack.addWidget(QLabel("No deadline"))
        self.due_date = DatePickerButton(task.due_date or date.today())
        self.deadline_stack.addWidget(self.due_date)
        self.due_at = DateTimePickerButton(task.due_at or _next_quarter(timezone_name), timezone_name)
        self.deadline_stack.addWidget(self.due_at)
        self.deadline_kind.currentIndexChanged.connect(self.deadline_stack.setCurrentIndex)
        self.deadline_stack.setCurrentIndex(self.deadline_kind.currentIndex())
        form.addRow("", self.deadline_stack)
        earliest_row = QWidget()
        earliest_layout = QHBoxLayout(earliest_row)
        earliest_layout.setContentsMargins(0, 0, 0, 0)
        earliest_layout.setSpacing(8)
        self.earliest_kind = QComboBox()
        self.earliest_kind.addItem("Available now", False)
        self.earliest_kind.addItem("Defer until…", True)
        earliest_layout.addWidget(self.earliest_kind)
        self.earliest_start = DateTimePickerButton(
            task.earliest_start_at or _next_quarter(timezone_name),
            timezone_name,
        )
        has_future_start = (
            task.earliest_start_at is not None
            and task.earliest_start_at > datetime.now(ZoneInfo("UTC"))
        )
        self.earliest_kind.setCurrentIndex(1 if has_future_start else 0)
        self.earliest_start.setVisible(has_future_start)
        self.earliest_kind.currentIndexChanged.connect(
            lambda _index: self.earliest_start.setVisible(bool(self.earliest_kind.currentData()))
        )
        earliest_layout.addWidget(self.earliest_start, 1)
        form.addRow("Available", earliest_row)
        self.description = QTextEdit(task.description or "")
        self.description.setPlaceholderText("Optional context and working details")
        self.description.setMaximumHeight(110)
        form.addRow("Description", self.description)
        self.can_split = QComboBox()
        self.can_split.addItem("Can split into blocks", True)
        self.can_split.addItem("Keep as one block", False)
        self.can_split.setCurrentIndex(0 if task.can_split else 1)
        form.addRow("Planning", self.can_split)
        self.minimum_block = OptionalMinutesInput(
            task.minimum_block_minutes_override,
            inherited_label="Use the global minimum block size",
        )
        self.maximum_block = OptionalMinutesInput(
            task.maximum_block_minutes_override,
            inherited_label="Use the global maximum block size",
        )
        form.addRow("Minimum block", self.minimum_block)
        form.addRow("Maximum block", self.maximum_block)
        self.post_due_policy = QComboBox()
        self.post_due_policy.addItem("Use Area default", None)
        self.post_due_policy.addItem("Ask me", PostDuePolicy.ASK)
        self.post_due_policy.addItem("Allow work after due date", PostDuePolicy.ALLOW)
        self.post_due_policy.addItem("Never schedule after due date", PostDuePolicy.FORBID)
        policy_index = self.post_due_policy.findData(task.post_due_policy_override)
        self.post_due_policy.setCurrentIndex(max(0, policy_index))
        form.addRow("After due date", self.post_due_policy)
        self.can_split.currentIndexChanged.connect(self._planning_mode_changed)
        self._planning_mode_changed()
        form.addRow(_dialog_buttons(self, self._validate))
        self.title.selectAll()
        self.title.setFocus()

    def _validate(self) -> None:
        if not self.title.text().strip():
            QMessageBox.warning(self, "Task needs a title", "Enter a title before saving.")
            return
        if (
            self.can_split.currentData()
            and self.minimum_block.value is not None
            and self.maximum_block.value is not None
            and self.minimum_block.value > self.maximum_block.value
        ):
            QMessageBox.warning(
                self,
                "Invalid block sizes",
                "The maximum block size must be at least the minimum block size.",
            )
            return
        self.accept()

    def _planning_mode_changed(self) -> None:
        can_split = bool(self.can_split.currentData())
        self.minimum_block.setEnabled(can_split)
        self.maximum_block.setEnabled(can_split)

    @property
    def value(self) -> TaskUpdate:
        kind = DeadlineKind(self.deadline_kind.currentData())
        can_split = bool(self.can_split.currentData())
        policy = self.post_due_policy.currentData()
        return TaskUpdate(
            title=self.title.text(),
            area_id=self.area.currentData(),
            description=self.description.toPlainText().strip() or None,
            deadline_kind=kind,
            due_date=self.due_date.value if kind is DeadlineKind.DATE else None,
            due_at=self.due_at.value if kind is DeadlineKind.DATETIME else None,
            earliest_start_at=self.earliest_start.value if self.earliest_kind.currentData() else None,
            estimated_remaining_seconds=self.estimate.seconds,
            priority=self.priority.currentData(),
            can_split=can_split,
            minimum_block_minutes_override=self.minimum_block.value if can_split else None,
            maximum_block_minutes_override=self.maximum_block.value if can_split else None,
            post_due_policy_override=PostDuePolicy(policy) if policy is not None else None,
        )


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
              <li>Search and filter open tasks, then update remaining work, defer, edit, or complete them.</li>
              <li>Create, inspect, edit, move, resize, and cancel events in day, week, and month views.</li>
              <li>Create Areas, archive or restore them, review change History, and inspect read-only DTOs in Debug mode.</li>
              <li>Configure defaults that later scheduler versions will use.</li>
            </ul>
            <h3>Calendar tips</h3>
            <ul>
              <li>Drag across empty space in Day or Week to create a block for that exact range.</li>
              <li>Drag a timed event in Day or Week to move it while preserving its duration.</li>
              <li>Drag either top corner/edge to change a timed event's start, or either bottom corner/edge to change its end.</li>
              <li>Double-click empty space to create a one-hour block.</li>
              <li>Double-click an event, or select it and choose <b>Edit selected</b>, to change it.</li>
              <li>The all-day editor uses an inclusive “Last day” field.</li>
            </ul>
            <h3>Keyboard shortcuts</h3>
            <table cellspacing="7">
              <tr><td><b>⌘⇧Space</b></td><td>Quick Capture</td></tr>
              <tr><td><b>⌘⇧H</b></td><td>Open this help</td></tr>
              <tr><td><b>⌘⇧S</b></td><td>Open Settings</td></tr>
              <tr><td><b>⌘⇧D</b></td><td>Toggle Debug Inspector</td></tr>
            </table>
            """
        )
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

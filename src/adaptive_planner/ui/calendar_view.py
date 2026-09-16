"""Native Qt day, week, and month calendar views."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_planner.domain.types import Availability, CalendarEventDTO
from adaptive_planner.ui.calendar_model import (
    CalendarMode,
    calendar_range,
    period_title,
    place_overlapping_events,
    query_bounds,
    split_events_by_day,
)


BACKGROUND = QColor("#ffffff")
GRID = QColor("#e5e9f0")
GRID_LIGHT = QColor("#f0f2f6")
TEXT = QColor("#344054")
MUTED = QColor("#7a8699")
OUTSIDE_MONTH = QColor("#a8b0bd")
TODAY = QColor("#2563eb")
TODAY_TINT = QColor("#eef4ff")
BUSY_FILL = QColor("#dce8ff")
BUSY_BORDER = QColor("#7da2ef")
BUSY_TEXT = QColor("#1849a9")
FREE_FILL = QColor("#f4f6f8")
FREE_BORDER = QColor("#aeb8c7")
FREE_TEXT = QColor("#475467")
SELECTED_BORDER = QColor("#173d8f")
NOW = QColor("#d92d20")
EVENT_DATA_ROLE = 0


def _font(size: int, *, bold: bool = False) -> QFont:
    font = QFont()
    font.setPixelSize(size)
    font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return font


def _elide(text: str, width: float, font: QFont) -> str:
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, max(1, int(width)))


def _event_colors(event: CalendarEventDTO) -> tuple[QColor, QColor, QColor]:
    if event.availability is Availability.FREE:
        return FREE_FILL, FREE_BORDER, FREE_TEXT
    return BUSY_FILL, BUSY_BORDER, BUSY_TEXT


def _add_event_chip(
    scene: QGraphicsScene,
    rect: QRectF,
    event: CalendarEventDTO,
    label: str,
    *,
    selected: bool,
    compact: bool = False,
) -> None:
    fill, border, foreground = _event_colors(event)
    outline = SELECTED_BORDER if selected else border
    box = scene.addRect(rect, QPen(outline, 2 if selected else 1), QBrush(fill))
    box.setData(EVENT_DATA_ROLE, str(event.id))
    box.setToolTip(label)
    font = _font(10 if compact else 11, bold=True)
    shown = _elide(label, rect.width() - 10, font)
    text_item = scene.addSimpleText(shown, font)
    text_item.setBrush(QBrush(foreground))
    text_item.setPos(rect.x() + 5, rect.y() + (2 if compact else 4))
    text_item.setData(EVENT_DATA_ROLE, str(event.id))
    text_item.setToolTip(label)


class _EventGraphicsView(QGraphicsView):
    eventClicked = Signal(str)
    eventDoubleClicked = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QBrush(BACKGROUND))
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setMouseTracking(True)

    def _event_id_at(self, point: QPoint) -> str | None:
        item = self.itemAt(point)
        while item is not None:
            value = item.data(EVENT_DATA_ROLE)
            if value:
                return str(value)
            item = item.parentItem()
        return None

    def mousePressEvent(self, event) -> None:
        event_id = self._event_id_at(event.position().toPoint())
        super().mousePressEvent(event)
        self.eventClicked.emit(event_id or "")

    def mouseDoubleClickEvent(self, event) -> None:
        event_id = self._event_id_at(event.position().toPoint())
        if event_id:
            self.eventDoubleClicked.emit(event_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _DayHeaderView(_EventGraphicsView):
    HEADER_HEIGHT = 68
    GUTTER = 62

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEADER_HEIGHT)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


class _TimeCanvas(_EventGraphicsView):
    emptyDoubleClicked = Signal(object, object)
    HOUR_HEIGHT = 52
    GUTTER = 62

    def __init__(self, owner: "TimeGridCalendar", parent=None) -> None:
        super().__init__(parent)
        self.owner = owner
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def mouseDoubleClickEvent(self, event) -> None:
        point = event.position().toPoint()
        event_id = self._event_id_at(point)
        if event_id:
            self.eventDoubleClicked.emit(event_id)
            event.accept()
            return
        scene_point = self.mapToScene(point)
        days = self.owner.visible.days
        usable_width = max(1.0, self.sceneRect().width() - self.GUTTER)
        column_width = usable_width / len(days)
        column = int((scene_point.x() - self.GUTTER) // column_width)
        if column < 0 or column >= len(days):
            return
        minute = int(scene_point.y() / self.HOUR_HEIGHT * 60)
        minute = max(0, min(23 * 60 + 45, (minute // 15) * 15))
        local_start = datetime.combine(days[column], time.min, tzinfo=self.owner.zone) + timedelta(minutes=minute)
        self.emptyDoubleClicked.emit(
            local_start.astimezone(timezone.utc),
            (local_start + timedelta(hours=1)).astimezone(timezone.utc),
        )
        event.accept()


class TimeGridCalendar(QWidget):
    """A one- or seven-column calendar with a scrollable 24-hour time grid."""

    eventClicked = Signal(str)
    eventDoubleClicked = Signal(str)
    emptyDoubleClicked = Signal(object, object)

    def __init__(self, mode: CalendarMode, parent=None) -> None:
        super().__init__(parent)
        if mode not in (CalendarMode.DAY, CalendarMode.WEEK):
            raise ValueError("TimeGridCalendar supports day and week modes")
        self.mode = mode
        self.anchor = date.today()
        self.timezone_name = "UTC"
        self.zone = ZoneInfo("UTC")
        self.events: tuple[CalendarEventDTO, ...] = ()
        self.selected_id: UUID | None = None
        self._needs_initial_scroll = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = _DayHeaderView(self)
        self.canvas = _TimeCanvas(self, self)
        self.header.eventClicked.connect(self.eventClicked)
        self.header.eventDoubleClicked.connect(self.eventDoubleClicked)
        self.canvas.eventClicked.connect(self.eventClicked)
        self.canvas.eventDoubleClicked.connect(self.eventDoubleClicked)
        self.canvas.emptyDoubleClicked.connect(self.emptyDoubleClicked)
        layout.addWidget(self.header)
        layout.addWidget(self.canvas, 1)

    @property
    def visible(self):
        return calendar_range(self.anchor, self.mode)

    def set_data(
        self,
        anchor: date,
        timezone_name: str,
        events: tuple[CalendarEventDTO, ...],
        selected_id: UUID | None,
    ) -> None:
        anchor_changed = anchor != self.anchor or timezone_name != self.timezone_name
        self.anchor = anchor
        self.timezone_name = timezone_name
        self.zone = ZoneInfo(timezone_name)
        self.events = events
        self.selected_id = selected_id
        self._needs_initial_scroll = self._needs_initial_scroll or anchor_changed
        self._render()
        if self._needs_initial_scroll:
            QTimer.singleShot(0, self._scroll_to_useful_time)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render()

    def _scene_width(self) -> float:
        minimum = 680 if self.mode is CalendarMode.WEEK else 460
        return max(float(minimum), float(self.canvas.viewport().width() - 2))

    def _render(self) -> None:
        width = self._scene_width()
        self._render_header(width)
        self._render_grid(width)

    def _render_header(self, width: float) -> None:
        scene = QGraphicsScene(self.header)
        scene.setSceneRect(0, 0, width, _DayHeaderView.HEADER_HEIGHT - 1)
        scene.setBackgroundBrush(BACKGROUND)
        days = self.visible.days
        column_width = (width - _DayHeaderView.GUTTER) / len(days)
        today = datetime.now(self.zone).date()
        slices = split_events_by_day(self.events, self.visible, self.timezone_name)

        scene.addLine(0, 38, width, 38, QPen(GRID))
        scene.addLine(0, 67, width, 67, QPen(GRID))
        all_day_label = scene.addSimpleText("ALL-DAY", _font(9, bold=True))
        all_day_label.setBrush(QBrush(MUTED))
        all_day_label.setPos(7, 46)
        for index, day in enumerate(days):
            left = _DayHeaderView.GUTTER + index * column_width
            if day == today:
                scene.addRect(left, 0, column_width, 38, Qt.PenStyle.NoPen, QBrush(TODAY_TINT))
            scene.addLine(left, 0, left, 68, QPen(GRID))
            label = day.strftime("%A, %B %-d") if self.mode is CalendarMode.DAY else day.strftime("%a  %-d")
            date_item = scene.addSimpleText(label, _font(12, bold=day == today))
            date_item.setBrush(QBrush(TODAY if day == today else TEXT))
            date_item.setPos(left + 8, 9)
            all_day = [item for item in slices[day] if item.all_day]
            if all_day:
                item = all_day[0]
                extra = f"  +{len(all_day) - 1}" if len(all_day) > 1 else ""
                _add_event_chip(
                    scene,
                    QRectF(left + 4, 41, column_width - 8, 23),
                    item.event,
                    item.event.title + extra,
                    selected=item.event.id == self.selected_id,
                    compact=True,
                )
        scene.addLine(width - 1, 0, width - 1, 68, QPen(GRID))
        self.header.setScene(scene)

    def _render_grid(self, width: float) -> None:
        scene = QGraphicsScene(self.canvas)
        height = 24 * _TimeCanvas.HOUR_HEIGHT
        scene.setSceneRect(0, 0, width, height)
        scene.setBackgroundBrush(BACKGROUND)
        days = self.visible.days
        column_width = (width - _TimeCanvas.GUTTER) / len(days)
        slices = split_events_by_day(self.events, self.visible, self.timezone_name)

        for hour in range(24):
            y = hour * _TimeCanvas.HOUR_HEIGHT
            scene.addLine(_TimeCanvas.GUTTER, y, width, y, QPen(GRID))
            if hour:
                label = datetime(2000, 1, 1, hour).strftime("%-I %p")
                time_item = scene.addSimpleText(label, _font(9))
                time_item.setBrush(QBrush(MUTED))
                time_item.setPos(8, y - 8)
            half_y = y + _TimeCanvas.HOUR_HEIGHT / 2
            scene.addLine(_TimeCanvas.GUTTER, half_y, width, half_y, QPen(GRID_LIGHT))
        scene.addLine(_TimeCanvas.GUTTER, 0, _TimeCanvas.GUTTER, height, QPen(GRID))

        for index, day in enumerate(days):
            left = _TimeCanvas.GUTTER + index * column_width
            scene.addLine(left, 0, left, height, QPen(GRID))
            for placement in place_overlapping_events(slices[day]):
                item = placement.slice
                gap = 3.0
                available = column_width - 8
                event_width = available / placement.column_count
                x = left + 4 + placement.column * event_width
                y = item.start_minute / 60 * _TimeCanvas.HOUR_HEIGHT + 1
                raw_height = (item.end_minute - item.start_minute) / 60 * _TimeCanvas.HOUR_HEIGHT - 2
                event_height = max(20.0, raw_height)
                local_start = item.event.start_at.astimezone(self.zone) if item.event.start_at else None
                time_text = local_start.strftime("%-I:%M %p") if local_start else ""
                label = (
                    item.event.title
                    if event_width < 115
                    else f"{time_text}  {item.event.title}".strip()
                )
                _add_event_chip(
                    scene,
                    QRectF(x, y, max(18.0, event_width - gap), event_height),
                    item.event,
                    label,
                    selected=item.event.id == self.selected_id,
                    compact=event_height < 32,
                )

        now = datetime.now(self.zone)
        if now.date() in days:
            index = days.index(now.date())
            left = _TimeCanvas.GUTTER + index * column_width
            y = (now.hour * 60 + now.minute + now.second / 60) / 60 * _TimeCanvas.HOUR_HEIGHT
            scene.addLine(left, y, left + column_width, y, QPen(NOW, 2))
            scene.addEllipse(left - 3, y - 3, 6, 6, Qt.PenStyle.NoPen, QBrush(NOW))
        self.canvas.setScene(scene)

    def _scroll_to_useful_time(self) -> None:
        if not self._needs_initial_scroll:
            return
        self._needs_initial_scroll = False
        now = datetime.now(self.zone)
        target_hour = max(0, (now.hour - 2) if now.date() in self.visible.days else 7)
        self.canvas.verticalScrollBar().setValue(target_hour * _TimeCanvas.HOUR_HEIGHT)


class MonthCalendar(_EventGraphicsView):
    emptyDoubleClicked = Signal(object, object)
    WEEKDAY_HEIGHT = 28

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.anchor = date.today()
        self.timezone_name = "UTC"
        self.zone = ZoneInfo("UTC")
        self.events: tuple[CalendarEventDTO, ...] = ()
        self.selected_id: UUID | None = None
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    @property
    def visible(self):
        return calendar_range(self.anchor, CalendarMode.MONTH)

    def set_data(
        self,
        anchor: date,
        timezone_name: str,
        events: tuple[CalendarEventDTO, ...],
        selected_id: UUID | None,
    ) -> None:
        self.anchor = anchor
        self.timezone_name = timezone_name
        self.zone = ZoneInfo(timezone_name)
        self.events = events
        self.selected_id = selected_id
        self._render()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render()

    def _render(self) -> None:
        width = max(560.0, float(self.viewport().width() - 2))
        height = max(400.0, float(self.viewport().height() - 2))
        scene = QGraphicsScene(self)
        scene.setSceneRect(0, 0, width, height)
        scene.setBackgroundBrush(BACKGROUND)
        column_width = width / 7
        row_height = (height - self.WEEKDAY_HEIGHT) / 6
        today = datetime.now(self.zone).date()
        slices = split_events_by_day(self.events, self.visible, self.timezone_name)

        for index, weekday in enumerate(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")):
            item = scene.addSimpleText(weekday, _font(9, bold=True))
            item.setBrush(QBrush(MUTED))
            item.setPos(index * column_width + 8, 6)
        scene.addLine(0, self.WEEKDAY_HEIGHT, width, self.WEEKDAY_HEIGHT, QPen(GRID))

        for offset, day in enumerate(self.visible.days):
            row, column = divmod(offset, 7)
            left = column * column_width
            top = self.WEEKDAY_HEIGHT + row * row_height
            if day == today:
                scene.addRect(left + 1, top + 1, column_width - 2, row_height - 2, Qt.PenStyle.NoPen, QBrush(TODAY_TINT))
            scene.addRect(left, top, column_width, row_height, QPen(GRID), Qt.BrushStyle.NoBrush)
            in_month = day.month == self.anchor.month
            day_item = scene.addSimpleText(str(day.day), _font(11, bold=day == today))
            day_item.setBrush(QBrush(TODAY if day == today else (TEXT if in_month else OUTSIDE_MONTH)))
            day_item.setPos(left + 7, top + 5)

            event_slices = slices[day]
            available_rows = max(1, min(3, int((row_height - 31) // 21)))
            for event_index, event_slice in enumerate(event_slices[:available_rows]):
                event = event_slice.event
                if event_slice.all_day:
                    label = event.title
                else:
                    local_start = event.start_at.astimezone(self.zone) if event.start_at else None
                    prefix = local_start.strftime("%-I:%M") if local_start else ""
                    label = f"{prefix}  {event.title}".strip()
                _add_event_chip(
                    scene,
                    QRectF(left + 5, top + 27 + event_index * 21, column_width - 10, 18),
                    event,
                    label,
                    selected=event.id == self.selected_id,
                    compact=True,
                )
            hidden = len(event_slices) - available_rows
            if hidden > 0:
                more = scene.addSimpleText(f"+{hidden} more", _font(9, bold=True))
                more.setBrush(QBrush(MUTED))
                more.setPos(left + 8, top + 27 + available_rows * 21)
        self.setScene(scene)

    def mouseDoubleClickEvent(self, event) -> None:
        point = event.position().toPoint()
        event_id = self._event_id_at(point)
        if event_id:
            self.eventDoubleClicked.emit(event_id)
            event.accept()
            return
        scene_point = self.mapToScene(point)
        if scene_point.y() < self.WEEKDAY_HEIGHT:
            return
        width = self.sceneRect().width()
        height = self.sceneRect().height()
        column = int(scene_point.x() // (width / 7))
        row = int((scene_point.y() - self.WEEKDAY_HEIGHT) // ((height - self.WEEKDAY_HEIGHT) / 6))
        offset = row * 7 + column
        if not 0 <= offset < 42:
            return
        chosen = self.visible.start + timedelta(days=offset)
        local_start = datetime.combine(chosen, time(hour=9), tzinfo=self.zone)
        self.emptyDoubleClicked.emit(
            local_start.astimezone(timezone.utc),
            (local_start + timedelta(hours=1)).astimezone(timezone.utc),
        )
        event.accept()


class CalendarView(QWidget):
    """Calendar controller and navigation shared by all three native views."""

    rangeChanged = Signal()
    eventSelected = Signal(object)
    eventEditRequested = Signal(object)
    blockTimeRequested = Signal(object, object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mode = CalendarMode.WEEK
        self.timezone_name = "UTC"
        self.zone = ZoneInfo("UTC")
        self.anchor = datetime.now(self.zone).date()
        self.events: tuple[CalendarEventDTO, ...] = ()
        self._events_by_id: dict[UUID, CalendarEventDTO] = {}
        self.selected_event: CalendarEventDTO | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        previous = QPushButton("‹")
        previous.setObjectName("calendarNavButton")
        previous.setToolTip("Previous period")
        previous.setAccessibleName("Previous period")
        previous.clicked.connect(lambda: self.navigate(-1))
        toolbar.addWidget(previous)
        today = QPushButton("Today")
        today.setObjectName("calendarNavButton")
        today.clicked.connect(self.go_to_today)
        toolbar.addWidget(today)
        following = QPushButton("›")
        following.setObjectName("calendarNavButton")
        following.setToolTip("Next period")
        following.setAccessibleName("Next period")
        following.clicked.connect(lambda: self.navigate(1))
        toolbar.addWidget(following)
        self.period_label = QLabel()
        self.period_label.setObjectName("calendarPeriod")
        toolbar.addWidget(self.period_label)
        toolbar.addStretch()
        self.timezone_label = QLabel()
        self.timezone_label.setObjectName("calendarTimezone")
        toolbar.addWidget(self.timezone_label)

        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self._mode_buttons: dict[CalendarMode, QPushButton] = {}
        for mode, label in (
            (CalendarMode.DAY, "Day"),
            (CalendarMode.WEEK, "Week"),
            (CalendarMode.MONTH, "Month"),
        ):
            button = QPushButton(label)
            button.setObjectName("calendarModeButton")
            button.setCheckable(True)
            button.setChecked(mode is self.mode)
            button.clicked.connect(lambda _checked=False, value=mode: self.set_mode(value))
            self.mode_group.addButton(button)
            self._mode_buttons[mode] = button
            toolbar.addWidget(button)
        layout.addLayout(toolbar)

        self.stack = QStackedWidget()
        self.day_view = TimeGridCalendar(CalendarMode.DAY)
        self.week_view = TimeGridCalendar(CalendarMode.WEEK)
        self.month_view = MonthCalendar()
        self._views = {
            CalendarMode.DAY: self.day_view,
            CalendarMode.WEEK: self.week_view,
            CalendarMode.MONTH: self.month_view,
        }
        for view in self._views.values():
            view.eventClicked.connect(self._select_event)
            view.eventDoubleClicked.connect(self._request_event_edit)
            view.emptyDoubleClicked.connect(self.blockTimeRequested)
            self.stack.addWidget(view)
        layout.addWidget(self.stack, 1)

        self.hint = QLabel()
        self.hint.setObjectName("calendarHint")
        layout.addWidget(self.hint)
        self._update_views()

    @property
    def visible(self):
        return calendar_range(self.anchor, self.mode)

    def visible_utc_range(self) -> tuple[datetime, datetime]:
        return query_bounds(self.visible, self.timezone_name)

    def set_timezone(self, timezone_name: str) -> None:
        if timezone_name == self.timezone_name:
            return
        self.timezone_name = timezone_name
        self.zone = ZoneInfo(timezone_name)
        self._update_views()

    def set_events(self, events: tuple[CalendarEventDTO, ...]) -> None:
        slices = split_events_by_day(events, self.visible, self.timezone_name)
        visible_ids = {item.event.id for day in slices.values() for item in day}
        self.events = tuple(event for event in events if event.id in visible_ids)
        self._events_by_id = {event.id: event for event in self.events}
        if self.selected_event:
            self.selected_event = self._events_by_id.get(self.selected_event.id)
            self.eventSelected.emit(self.selected_event)
        self._update_views()

    def set_mode(self, mode: CalendarMode) -> None:
        self._mode_buttons[mode].setChecked(True)
        if mode is self.mode:
            return
        self.mode = mode
        self._update_views()
        self.rangeChanged.emit()

    def navigate(self, direction: int) -> None:
        if self.mode is CalendarMode.DAY:
            self.anchor += timedelta(days=direction)
        elif self.mode is CalendarMode.WEEK:
            self.anchor += timedelta(days=7 * direction)
        else:
            month_index = self.anchor.year * 12 + self.anchor.month - 1 + direction
            year, month_zero_based = divmod(month_index, 12)
            month = month_zero_based + 1
            self.anchor = self.anchor.replace(year=year, month=month, day=min(self.anchor.day, monthrange(year, month)[1]))
        self._update_views()
        self.rangeChanged.emit()

    def go_to_today(self) -> None:
        today = datetime.now(self.zone).date()
        if today == self.anchor:
            return
        self.anchor = today
        self._update_views()
        self.rangeChanged.emit()

    def _select_event(self, event_id: str) -> None:
        selected = self._events_by_id.get(UUID(event_id)) if event_id else None
        self.selected_event = selected
        self.eventSelected.emit(selected)
        self._update_views()

    def _request_event_edit(self, event_id: str) -> None:
        event = self._events_by_id.get(UUID(event_id))
        if event is not None:
            self.selected_event = event
            self.eventSelected.emit(event)
            self._update_views()
            self.eventEditRequested.emit(event)

    def _update_views(self) -> None:
        self.period_label.setText(period_title(self.anchor, self.mode))
        self.timezone_label.setText(self.timezone_name)
        selected_id = self.selected_event.id if self.selected_event else None
        view = self._views[self.mode]
        view.set_data(self.anchor, self.timezone_name, self.events, selected_id)
        self.stack.setCurrentWidget(view)
        noun = "event" if len(self.events) == 1 else "events"
        self.hint.setText(f"{len(self.events)} {noun} in view  •  Double-click empty space to block time")

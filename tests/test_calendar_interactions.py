from __future__ import annotations

import os
from datetime import date, datetime, timezone
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest

from adaptive_planner.domain.types import Availability, CalendarEventDTO, TimeKind
from adaptive_planner.ui.calendar_model import CalendarMode
from adaptive_planner.ui.calendar_view import TimeGridCalendar, _TimeCanvas


def _timed_event(start_hour: int, end_hour: int) -> CalendarEventDTO:
    now = datetime.now(timezone.utc)
    return CalendarEventDTO(
        id=uuid4(),
        area_id=None,
        title="Focus",
        description=None,
        time_kind=TimeKind.TIMED,
        availability=Availability.BUSY,
        start_at=datetime(2026, 9, 15, start_hour, tzinfo=timezone.utc),
        end_at=datetime(2026, 9, 15, end_hour, tzinfo=timezone.utc),
        start_date=None,
        end_date=None,
        timezone_name="UTC",
        cancelled_at=None,
        created_at=now,
        updated_at=now,
    )


def _scene_point(view: TimeGridCalendar, hour: float):
    return view.canvas.mapFromScene(QPointF(_TimeCanvas.GUTTER + 100, hour * _TimeCanvas.HOUR_HEIGHT))


def _event_corner(view: TimeGridCalendar, hour: float, *, right: bool = False):
    x = view.canvas.sceneRect().right() - 10 if right else _TimeCanvas.GUTTER + 8
    return view.canvas.mapFromScene(QPointF(x, hour * _TimeCanvas.HOUR_HEIGHT))


def test_dragging_empty_time_selects_an_outward_snapped_range(qtbot) -> None:
    view = TimeGridCalendar(CalendarMode.DAY)
    qtbot.addWidget(view)
    view.resize(800, 700)
    view.set_data(date(2026, 9, 15), "UTC", (), None)
    view.show()
    qtbot.wait(10)

    start = _scene_point(view, 9.1)
    end = _scene_point(view, 10.6)
    with qtbot.waitSignal(view.rangeDragged) as signal:
        QTest.mousePress(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.canvas.viewport(), end, 20)
        QTest.mouseRelease(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)

    assert signal.args == [
        datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 15, 10, 45, tzinfo=timezone.utc),
    ]


def test_dragging_timed_event_preserves_duration_and_grab_offset(qtbot) -> None:
    source = _timed_event(9, 10)
    view = TimeGridCalendar(CalendarMode.DAY)
    qtbot.addWidget(view)
    view.resize(800, 700)
    view.set_data(date(2026, 9, 15), "UTC", (source,), None)
    view.show()
    qtbot.wait(10)

    press = _scene_point(view, 9.5)
    drop = _scene_point(view, 11.5)
    with qtbot.waitSignal(view.eventMoveRequested) as signal:
        QTest.mousePress(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=press)
        QTest.mouseMove(view.canvas.viewport(), drop, 20)
        QTest.mouseRelease(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=drop)

    assert signal.args == [
        str(source.id),
        datetime(2026, 9, 15, 11, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    ]


def test_dragging_top_corner_resizes_event_start(qtbot) -> None:
    source = _timed_event(9, 10)
    view = TimeGridCalendar(CalendarMode.DAY)
    qtbot.addWidget(view)
    view.resize(800, 700)
    view.set_data(date(2026, 9, 15), "UTC", (source,), None)
    view.show()
    qtbot.wait(10)

    press = _event_corner(view, 9 + 3 / _TimeCanvas.HOUR_HEIGHT)
    drop = _event_corner(view, 8.5)
    with qtbot.waitSignal(view.eventResizeRequested) as signal:
        QTest.mousePress(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=press)
        QTest.mouseMove(view.canvas.viewport(), drop, 20)
        QTest.mouseRelease(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=drop)

    assert signal.args == [
        str(source.id),
        datetime(2026, 9, 15, 8, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
    ]


def test_dragging_bottom_corner_resizes_event_end(qtbot) -> None:
    source = _timed_event(9, 10)
    view = TimeGridCalendar(CalendarMode.DAY)
    qtbot.addWidget(view)
    view.resize(800, 700)
    view.set_data(date(2026, 9, 15), "UTC", (source,), None)
    view.show()
    qtbot.wait(10)

    press = _event_corner(view, 10 - 3 / _TimeCanvas.HOUR_HEIGHT, right=True)
    drop = _event_corner(view, 11.25, right=True)
    with qtbot.waitSignal(view.eventResizeRequested) as signal:
        QTest.mousePress(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=press)
        QTest.mouseMove(view.canvas.viewport(), drop, 20)
        QTest.mouseRelease(view.canvas.viewport(), Qt.MouseButton.LeftButton, pos=drop)

    assert signal.args == [
        str(source.id),
        datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 15, 11, 15, tzinfo=timezone.utc),
    ]

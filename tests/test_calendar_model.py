from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from adaptive_planner.domain.types import Availability, CalendarEventDTO, TimeKind
from adaptive_planner.ui.calendar_model import (
    CalendarMode,
    calendar_range,
    place_overlapping_events,
    query_bounds,
    split_events_by_day,
)


def _timed_event(title: str, start: datetime, end: datetime) -> CalendarEventDTO:
    now = datetime.now(timezone.utc)
    return CalendarEventDTO(
        id=uuid4(),
        area_id=None,
        title=title,
        description=None,
        time_kind=TimeKind.TIMED,
        availability=Availability.BUSY,
        start_at=start,
        end_at=end,
        start_date=None,
        end_date=None,
        timezone_name=None,
        cancelled_at=None,
        created_at=now,
        updated_at=now,
    )


def test_calendar_ranges_are_stable_and_monday_based() -> None:
    anchor = date(2026, 9, 15)
    assert calendar_range(anchor, CalendarMode.DAY).days == (anchor,)
    assert calendar_range(anchor, CalendarMode.WEEK).days[0] == date(2026, 9, 14)
    month = calendar_range(anchor, CalendarMode.MONTH)
    assert month.start == date(2026, 8, 31)
    assert month.end == date(2026, 10, 12)
    assert len(month.days) == 42


def test_query_bounds_respect_daylight_saving_transitions() -> None:
    visible = calendar_range(date(2026, 11, 1), CalendarMode.DAY)
    start, end = query_bounds(visible, "America/Indiana/Indianapolis")
    assert end - start == timedelta(hours=25)


def test_timed_events_are_split_at_local_midnight() -> None:
    zone = ZoneInfo("America/Indiana/Indianapolis")
    local_start = datetime(2026, 9, 15, 23, 30, tzinfo=zone)
    local_end = datetime(2026, 9, 16, 1, 0, tzinfo=zone)
    event = _timed_event(
        "Overnight",
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )
    visible = calendar_range(date(2026, 9, 15), CalendarMode.WEEK)

    slices = split_events_by_day((event,), visible, "America/Indiana/Indianapolis")

    first = slices[date(2026, 9, 15)][0]
    second = slices[date(2026, 9, 16)][0]
    assert (first.start_minute, first.end_minute) == (23.5 * 60, 24 * 60)
    assert first.continues_after is True
    assert (second.start_minute, second.end_minute) == (0, 60)
    assert second.continues_before is True


def test_overlapping_events_receive_separate_columns() -> None:
    zone = ZoneInfo("UTC")
    day = date(2026, 9, 15)
    first = _timed_event(
        "First",
        datetime(2026, 9, 15, 9, tzinfo=zone),
        datetime(2026, 9, 15, 11, tzinfo=zone),
    )
    second = _timed_event(
        "Second",
        datetime(2026, 9, 15, 10, tzinfo=zone),
        datetime(2026, 9, 15, 12, tzinfo=zone),
    )
    slices = split_events_by_day((first, second), calendar_range(day, CalendarMode.DAY), "UTC")

    placements = place_overlapping_events(slices[day])

    assert {placement.column for placement in placements} == {0, 1}
    assert {placement.column_count for placement in placements} == {2}

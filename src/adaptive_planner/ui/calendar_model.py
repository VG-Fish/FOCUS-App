"""Pure date-range and event-layout helpers for the native calendar UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Iterable
from zoneinfo import ZoneInfo

from adaptive_planner.domain.types import CalendarEventDTO, TimeKind


class CalendarMode(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


@dataclass(frozen=True)
class CalendarRange:
    """A visible local-date range with an exclusive end."""

    start: date
    end: date

    @property
    def days(self) -> tuple[date, ...]:
        return tuple(self.start + timedelta(days=offset) for offset in range((self.end - self.start).days))


@dataclass(frozen=True)
class EventSlice:
    """The portion of an event visible on one local calendar day."""

    event: CalendarEventDTO
    day: date
    start_minute: float
    end_minute: float
    all_day: bool
    continues_before: bool = False
    continues_after: bool = False


@dataclass(frozen=True)
class TimedPlacement:
    """An event slice plus its column in an overlapping-event group."""

    slice: EventSlice
    column: int
    column_count: int


def calendar_range(anchor: date, mode: CalendarMode) -> CalendarRange:
    if mode is CalendarMode.DAY:
        return CalendarRange(anchor, anchor + timedelta(days=1))
    if mode is CalendarMode.WEEK:
        start = anchor - timedelta(days=anchor.weekday())
        return CalendarRange(start, start + timedelta(days=7))
    first = anchor.replace(day=1)
    start = first - timedelta(days=first.weekday())
    # A stable six-row grid prevents the calendar from jumping in height.
    return CalendarRange(start, start + timedelta(days=42))


def query_bounds(visible: CalendarRange, timezone_name: str) -> tuple[datetime, datetime]:
    """Convert local calendar boundaries to exact UTC instants, including DST."""

    zone = ZoneInfo(timezone_name)
    start = datetime.combine(visible.start, time.min, tzinfo=zone)
    end = datetime.combine(visible.end, time.min, tzinfo=zone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def split_events_by_day(
    events: Iterable[CalendarEventDTO],
    visible: CalendarRange,
    timezone_name: str,
) -> dict[date, list[EventSlice]]:
    """Split timed and all-day events into local-day pieces for rendering."""

    zone = ZoneInfo(timezone_name)
    result: dict[date, list[EventSlice]] = {day: [] for day in visible.days}
    for event in events:
        if event.time_kind is TimeKind.ALL_DAY:
            if event.start_date is None or event.end_date is None:
                continue
            first = max(event.start_date, visible.start)
            last = min(event.end_date, visible.end)
            day = first
            while day < last:
                result[day].append(
                    EventSlice(
                        event=event,
                        day=day,
                        start_minute=0,
                        end_minute=24 * 60,
                        all_day=True,
                        continues_before=day > event.start_date,
                        continues_after=day + timedelta(days=1) < event.end_date,
                    )
                )
                day += timedelta(days=1)
            continue

        if event.start_at is None or event.end_at is None:
            continue
        local_start = event.start_at.astimezone(zone)
        local_end = event.end_at.astimezone(zone)
        first = max(local_start.date(), visible.start)
        final = min(local_end.date() + timedelta(days=1), visible.end)
        day = first
        while day < final:
            day_start = datetime.combine(day, time.min, tzinfo=zone)
            day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
            clipped_start = max(local_start, day_start)
            clipped_end = min(local_end, day_end)
            if clipped_end > clipped_start:
                result[day].append(
                    EventSlice(
                        event=event,
                        day=day,
                        start_minute=(clipped_start - day_start).total_seconds() / 60,
                        end_minute=(clipped_end - day_start).total_seconds() / 60,
                        all_day=False,
                        continues_before=local_start < day_start,
                        continues_after=local_end > day_end,
                    )
                )
            day += timedelta(days=1)

    for slices in result.values():
        slices.sort(key=lambda item: (not item.all_day, item.start_minute, item.event.title.casefold()))
    return result


def place_overlapping_events(slices: Iterable[EventSlice]) -> tuple[TimedPlacement, ...]:
    """Assign side-by-side columns to overlapping timed event slices."""

    timed = sorted(
        (item for item in slices if not item.all_day),
        key=lambda item: (item.start_minute, item.end_minute, item.event.title.casefold()),
    )
    groups: list[list[EventSlice]] = []
    current: list[EventSlice] = []
    group_end = -1.0
    for item in timed:
        if current and item.start_minute >= group_end:
            groups.append(current)
            current = []
            group_end = -1.0
        current.append(item)
        group_end = max(group_end, item.end_minute)
    if current:
        groups.append(current)

    placements: list[TimedPlacement] = []
    for group in groups:
        active: list[tuple[float, int]] = []
        assigned: list[tuple[EventSlice, int]] = []
        width = 1
        for item in group:
            active = [(end, column) for end, column in active if end > item.start_minute]
            occupied = {column for _end, column in active}
            column = 0
            while column in occupied:
                column += 1
            active.append((item.end_minute, column))
            assigned.append((item, column))
            width = max(width, len(active), column + 1)
        placements.extend(TimedPlacement(item, column, width) for item, column in assigned)
    return tuple(placements)


def period_title(anchor: date, mode: CalendarMode) -> str:
    if mode is CalendarMode.DAY:
        return anchor.strftime("%A, %B %-d, %Y")
    if mode is CalendarMode.WEEK:
        visible = calendar_range(anchor, mode)
        last = visible.end - timedelta(days=1)
        if visible.start.year != last.year:
            return f"{visible.start.strftime('%b %-d, %Y')} – {last.strftime('%b %-d, %Y')}"
        if visible.start.month != last.month:
            return f"{visible.start.strftime('%b %-d')} – {last.strftime('%b %-d, %Y')}"
        return f"{visible.start.strftime('%B %-d')}–{last.strftime('%-d, %Y')}"
    return anchor.strftime("%B %Y")

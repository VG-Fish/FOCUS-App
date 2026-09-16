from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from adaptive_planner.application.capture import parse_quick_capture
from adaptive_planner.application.planner import PlannerApp
from adaptive_planner.domain.types import (
    AreaCreate,
    Availability,
    CalendarEventCreate,
    CalendarEventUpdate,
    DeadlineKind,
    TaskCreate,
    TaskUpdate,
    TimeKind,
)


def test_quick_capture_is_deterministic_and_preserves_date_precision() -> None:
    parsed = parse_quick_capture(
        "Finish ECE lab\nDue: Friday\nEstimate: 1h 30m\nArea: ECE 362",
        today=date(2026, 9, 15),
    )
    assert parsed.title == "Finish ECE lab"
    assert parsed.area_name == "ECE 362"
    assert parsed.due_date == date(2026, 9, 18)
    assert parsed.estimate_minutes == 90


def test_v01_crud_history_and_inbox(tmp_path) -> None:
    db = tmp_path / "planner.db"
    app = PlannerApp(db)
    try:
        areas = app.list_areas()
        assert len(areas) == 1
        assert areas[0].system_key == "UNCATEGORIZED"
        assert areas[0].name == "None"

        task = app.create_task(TaskCreate(area_id=areas[0].id, title="Read paper"))
        assert app.get_inbox_count() == 1
        task = app.adjust_remaining(task.id, 45)
        assert task.estimated_remaining_minutes == 45
        task = app.update_task(task.id, TaskUpdate(priority=5))
        assert task.priority == 5
        app.complete_task(task.id)
        assert app.get_inbox_count() == 0
        assert [event.event_type for event in app.list_history(10)][:3] == [
            "TASK_COMPLETED",
            "TASK_UPDATED",
            "TASK_UPDATED",
        ]
    finally:
        app.close()

    # A second owner can reopen the same database after the first has closed it.
    second = PlannerApp(db)
    try:
        assert len(second.list_tasks(include_archived=True, include_completed=True)) == 1
    finally:
        second.close()


def test_date_deadline_and_calendar_shape_validation(tmp_path) -> None:
    app = PlannerApp(tmp_path / "planner.db")
    try:
        area = app.list_areas()[0]
        task = app.create_task(
            TaskCreate(
                area_id=area.id,
                title="Submit lab",
                deadline_kind=DeadlineKind.DATE,
                due_date=date(2026, 9, 18),
                estimated_remaining_minutes=120,
            )
        )
        assert task.due_date == date(2026, 9, 18)
        assert task.due_at is None

        now = datetime(2026, 9, 15, 14, 0, tzinfo=timezone.utc)
        event = app.create_event(
            CalendarEventCreate(
                title="Study group",
                time_kind=TimeKind.TIMED,
                start_at=now,
                end_at=now + timedelta(minutes=60),
            )
        )
        assert event.start_at == now
        event = app.update_event(
            event.id,
            CalendarEventUpdate(
                title="Study group · moved",
                availability=Availability.FREE,
                start_at=now + timedelta(hours=1),
                end_at=now + timedelta(hours=2),
            ),
        )
        assert event.title == "Study group · moved"
        assert event.availability is Availability.FREE
        assert event.start_at == now + timedelta(hours=1)
        assert app.list_history(1)[0].event_type == "CALENDAR_EVENT_UPDATED"
        event = app.update_event(
            event.id,
            CalendarEventUpdate(
                time_kind=TimeKind.ALL_DAY,
                start_at=None,
                end_at=None,
                start_date=date(2026, 9, 18),
                end_date=date(2026, 9, 20),
            ),
        )
        assert event.start_at is None
        assert event.start_date == date(2026, 9, 18)
        assert event.end_date == date(2026, 9, 20)
        with pytest.raises(ValueError, match="timed events"):
            CalendarEventCreate(title="Bad", time_kind=TimeKind.TIMED, start_at=now, end_at=now)
    finally:
        app.close()


def test_area_archive_requires_explicit_incomplete_task_action(tmp_path) -> None:
    app = PlannerApp(tmp_path / "planner.db")
    try:
        area = app.create_area(AreaCreate(name="Work"))
        task = app.create_task(TaskCreate(area_id=area.id, title="Open item", estimated_remaining_minutes=30))
        with pytest.raises(ValueError, match="incomplete Tasks"):
            app.archive_area(area.id)
        app.archive_area(area.id, action="archive_contents")
        assert app.inspect_task(task.id).archived_at is not None
    finally:
        app.close()

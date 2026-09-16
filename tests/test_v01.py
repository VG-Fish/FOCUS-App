from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import sqlite3

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
        task = app.adjust_remaining_seconds(task.id, 45)
        assert task.estimated_remaining_seconds == 45
        task = app.update_task(task.id, TaskUpdate(priority=5))
        assert task.priority == 5
        app.complete_task(task.id)
        assert app.get_inbox_count() == 0
        assert [event.event_type for event in app.list_history(10)][:3] == [
            "TASK_COMPLETED",
            "TASK_UPDATED",
            "TASK_UPDATED",
        ]
        priority_change = app.list_history(10)[1]
        assert priority_change.before == {"priority": 3}
        assert priority_change.after == {"priority": 5}
    finally:
        app.close()

    # A second owner can reopen the same database after the first has closed it.
    second = PlannerApp(db)
    try:
        assert len(second.list_tasks(include_archived=True, include_completed=True)) == 1
    finally:
        second.close()


def test_task_archive_restore_complete_and_reopen_are_reversible(tmp_path) -> None:
    app = PlannerApp(tmp_path / "planner.db")
    try:
        area = app.list_areas()[0]
        task = app.create_task(TaskCreate(area_id=area.id, title="Reversible task"))

        completed = app.complete_task(task.id)
        assert completed.completed_at is not None
        assert app.reopen_task(task.id).completed_at is None

        archived = app.archive_task(task.id)
        assert archived.archived_at is not None
        assert app.restore_task(task.id).archived_at is None
        assert [event.event_type for event in app.list_history(4)] == [
            "TASK_RESTORED",
            "TASK_ARCHIVED",
            "TASK_REOPENED",
            "TASK_COMPLETED",
        ]
    finally:
        app.close()


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
                estimated_remaining_seconds=120 * 60,
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


def test_calendar_work_block_archive_and_restore(tmp_path) -> None:
    app = PlannerApp(tmp_path / "planner.db")
    try:
        start = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
        event = app.block_time("Protected study", start, start + timedelta(hours=1))
        archived = app.archive_event(event.id)
        assert archived.archived_at is not None
        assert all(item.id != event.id for item in app.list_events())
        archived_events = app.list_events(include_archived=True)
        assert archived_events[0].archived_at is not None

        restored = app.restore_event(event.id)
        assert restored.archived_at is None
        assert any(item.id == event.id for item in app.list_events())
        assert app.list_history(1)[0].event_type == "CALENDAR_EVENT_RESTORED"
    finally:
        app.close()


def test_area_archive_requires_explicit_incomplete_task_action(tmp_path) -> None:
    app = PlannerApp(tmp_path / "planner.db")
    try:
        area = app.create_area(AreaCreate(name="Work"))
        task = app.create_task(TaskCreate(area_id=area.id, title="Open item", estimated_remaining_seconds=30 * 60))
        with pytest.raises(ValueError, match="incomplete Tasks"):
            app.archive_area(area.id)
        app.archive_area(area.id, action="archive_contents")
        assert app.inspect_task(task.id).archived_at is not None

        assert all(item.id != area.id for item in app.list_areas())
        archived = next(item for item in app.list_areas(include_archived=True) if item.id == area.id)
        assert archived.archived_at is not None

        restored = app.restore_area(area.id)
        assert restored.archived_at is None
        assert any(item.id == area.id for item in app.list_areas())
        assert app.inspect_task(task.id).archived_at is not None
        assert app.list_history(1)[0].event_type == "AREA_RESTORED"
    finally:
        app.close()


def test_restoring_area_rejects_an_active_name_conflict(tmp_path) -> None:
    app = PlannerApp(tmp_path / "planner.db")
    try:
        archived = app.create_area(AreaCreate(name="Work"))
        app.archive_area(archived.id)
        app.create_area(AreaCreate(name="Work"))

        with pytest.raises(ValueError, match="already exists"):
            app.restore_area(archived.id)
    finally:
        app.close()


def test_estimates_persist_exact_seconds_and_upgrade_minute_storage(tmp_path) -> None:
    db = tmp_path / "planner.db"
    app = PlannerApp(db)
    try:
        area = app.list_areas()[0]
        task = app.create_task(TaskCreate(area_id=area.id, title="Short task", estimated_remaining_seconds=45))
        assert app.inspect_task(task.id).estimated_remaining_seconds == 45
    finally:
        app.close()

    # Recreate the last v0.1 column/value shape and verify the migration turns
    # two stored minutes into 120 seconds without losing the task.
    connection = sqlite3.connect(db)
    try:
        connection.execute("UPDATE tasks SET estimated_remaining_seconds = 2 WHERE id = ?", (str(task.id),))
        connection.execute("ALTER TABLE tasks RENAME COLUMN estimated_remaining_seconds TO estimated_remaining_minutes")
        connection.execute("UPDATE alembic_version SET version_num = '0001_v01_foundation'")
        connection.commit()
    finally:
        connection.close()

    migrated = PlannerApp(db)
    try:
        assert migrated.inspect_task(task.id).estimated_remaining_seconds == 120
    finally:
        migrated.close()


def test_task_notes_are_merged_into_description_before_column_removal(tmp_path) -> None:
    db = tmp_path / "planner.db"
    app = PlannerApp(db)
    try:
        area = app.list_areas()[0]
        with_description = app.create_task(
            TaskCreate(area_id=area.id, title="With context", description="Original context")
        )
        notes_only = app.create_task(TaskCreate(area_id=area.id, title="Notes only"))
    finally:
        app.close()

    # Recreate the old v0.1 shape and verify the migration preserves content
    # while eliminating the duplicate task field.
    connection = sqlite3.connect(db)
    try:
        connection.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")
        connection.execute("UPDATE tasks SET notes = ? WHERE id = ?", ("Working detail", str(with_description.id)))
        connection.execute("UPDATE tasks SET notes = ? WHERE id = ?", ("Only detail", str(notes_only.id)))
        connection.execute("UPDATE alembic_version SET version_num = '0002_task_estimates_in_seconds'")
        connection.commit()
    finally:
        connection.close()

    migrated = PlannerApp(db)
    try:
        assert migrated.inspect_task(with_description.id).description == "Original context\n\nWorking detail"
        assert migrated.inspect_task(notes_only.id).description == "Only detail"
    finally:
        migrated.close()

    connection = sqlite3.connect(db)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}
        assert "notes" not in columns
    finally:
        connection.close()

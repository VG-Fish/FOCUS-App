"""UI-facing PlannerApp façade for v0.1."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from adaptive_planner.application.capture import parse_quick_capture
from adaptive_planner.domain.types import (
    AreaCreate,
    AreaDTO,
    Availability,
    CalendarEventCreate,
    CalendarEventDTO,
    CalendarEventUpdate,
    DeadlineKind,
    HistoryEventDTO,
    PlannerPreferencesDocument,
    TaskCreate,
    TaskDTO,
    TaskUpdate,
    TimeKind,
    TodayDTO,
)
from adaptive_planner.persistence.core_store import CoreStore, UNCATEGORIZED
from adaptive_planner.persistence.database import DatabaseWorker


class PlannerApp:
    """The only boundary the Qt UI needs to know about."""

    def __init__(self, db_path: Path | None = None) -> None:
        default_path = Path.home() / "Library" / "Application Support" / "Adaptive Planner" / "planner.db"
        self.database = DatabaseWorker(db_path or default_path)
        self.database.call(CoreStore.ensure_uncategorized)
        self.database.call(CoreStore.get_preferences)

    def close(self) -> None:
        self.database.close()

    def backup_now(self) -> Path:
        return self.database.backup_now()

    def get_preferences(self) -> PlannerPreferencesDocument:
        return self.database.call(CoreStore.get_preferences)

    def update_preferences(self, document: PlannerPreferencesDocument) -> PlannerPreferencesDocument:
        return self.database.call(lambda session: CoreStore.update_preferences(session, document))

    def list_areas(self, include_archived: bool = False) -> tuple[AreaDTO, ...]:
        return self.database.call(lambda session: CoreStore.list_areas(session, include_archived))

    def create_area(self, data: AreaCreate) -> AreaDTO:
        return self.database.call(lambda session: CoreStore.create_area(session, data))

    def rename_area(self, area_id: UUID, name: str) -> AreaDTO:
        return self.database.call(lambda session: CoreStore.rename_area(session, area_id, name))

    def update_area(self, area_id: UUID, data: AreaCreate) -> AreaDTO:
        return self.database.call(lambda session: CoreStore.update_area(session, area_id, data))

    def archive_area(self, area_id: UUID, action: str = "area_only", destination_area_id: UUID | None = None) -> None:
        self.database.call(lambda session: CoreStore.archive_area(session, area_id, action, destination_area_id))

    def restore_area(self, area_id: UUID) -> AreaDTO:
        return self.database.call(lambda session: CoreStore.restore_area(session, area_id))

    def list_tasks(
        self,
        *,
        inbox_only: bool = False,
        include_archived: bool = False,
        include_completed: bool = False,
    ) -> tuple[TaskDTO, ...]:
        return self.database.call(
            lambda session: CoreStore.list_tasks(
                session,
                inbox_only=inbox_only,
                include_archived=include_archived,
                include_completed=include_completed,
            )
        )

    def create_task(self, data: TaskCreate) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.create_task(session, data))

    def update_task(self, task_id: UUID, changes: TaskUpdate) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.update_task(session, task_id, changes))

    def complete_task(self, task_id: UUID) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.complete_task(session, task_id))

    def reopen_task(self, task_id: UUID) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.reopen_task(session, task_id))

    def archive_task(self, task_id: UUID) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.archive_task(session, task_id))

    def restore_task(self, task_id: UUID) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.restore_task(session, task_id))

    def adjust_remaining(self, task_id: UUID, minutes: int | None) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.adjust_remaining(session, task_id, minutes))

    def adjust_remaining_seconds(self, task_id: UUID, seconds: int | None) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.adjust_remaining_seconds(session, task_id, seconds))

    def defer_task(self, task_id: UUID, earliest_start_at: datetime | None) -> TaskDTO:
        return self.database.call(lambda session: CoreStore.defer_task(session, task_id, earliest_start_at))

    def list_events(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
        include_archived: bool = False,
    ) -> tuple[CalendarEventDTO, ...]:
        return self.database.call(
            lambda session: CoreStore.list_events(
                session,
                start=start,
                end=end,
                include_cancelled=include_cancelled,
                include_archived=include_archived,
            )
        )

    def create_event(self, data: CalendarEventCreate) -> CalendarEventDTO:
        return self.database.call(lambda session: CoreStore.create_event(session, data))

    def update_event(self, event_id: UUID, changes: CalendarEventUpdate) -> CalendarEventDTO:
        return self.database.call(lambda session: CoreStore.update_event(session, event_id, changes))

    def cancel_event(self, event_id: UUID) -> CalendarEventDTO:
        return self.database.call(lambda session: CoreStore.cancel_event(session, event_id))

    def archive_event(self, event_id: UUID) -> CalendarEventDTO:
        return self.database.call(lambda session: CoreStore.archive_event(session, event_id))

    def restore_event(self, event_id: UUID) -> CalendarEventDTO:
        return self.database.call(lambda session: CoreStore.restore_event(session, event_id))

    def block_time(self, title: str, start_at: datetime, end_at: datetime, description: str | None = None) -> CalendarEventDTO:
        return self.create_event(
            CalendarEventCreate(
                title=title,
                description=description,
                time_kind=TimeKind.TIMED,
                availability=Availability.BUSY,
                start_at=start_at,
                end_at=end_at,
            )
        )

    def list_history(self, limit: int = 100) -> tuple[HistoryEventDTO, ...]:
        return self.database.call(lambda session: CoreStore.list_history(session, limit))

    def get_today(self, now: datetime | None = None) -> TodayDTO:
        return self.database.call(lambda session: CoreStore.today(session, now))

    def quick_capture(self, text: str, now: datetime | None = None) -> TaskDTO:
        preferences = self.get_preferences()
        current = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(preferences.timezone_name))
        parsed = parse_quick_capture(text, today=current.date())
        areas = self.list_areas()
        area = next((item for item in areas if item.name.casefold() == (parsed.area_name or "").casefold()), None)
        if parsed.area_name and area is None:
            area = self.create_area(AreaCreate(name=parsed.area_name))
        if area is None:
            area = next(item for item in areas if item.system_key == UNCATEGORIZED)
        deadline_kind = DeadlineKind.DATE if parsed.due_date else DeadlineKind.NONE
        return self.create_task(
            TaskCreate(
                area_id=area.id,
                title=parsed.title,
                deadline_kind=deadline_kind,
                due_date=parsed.due_date,
                estimated_remaining_seconds=None if parsed.estimate_minutes is None else parsed.estimate_minutes * 60,
            )
        )

    def get_inbox_count(self) -> int:
        return len(self.list_tasks(inbox_only=True))

    def inspect_task(self, task_id: UUID) -> TaskDTO:
        task = next((item for item in self.list_tasks(include_archived=True, include_completed=True) if item.id == task_id), None)
        if task is None:
            raise ValueError("Task not found")
        return task

    def inspect_event(self, event_id: UUID) -> CalendarEventDTO:
        return self.database.call(lambda session: CoreStore.get_event(session, event_id))

"""Behavior-oriented persistence operations used by PlannerApp."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, overload
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from adaptive_planner.domain.types import (
    AreaCreate,
    AreaDTO,
    AreaKind,
    Availability,
    CalendarEventCreate,
    CalendarEventDTO,
    CalendarEventUpdate,
    DeadlineKind,
    HistoryEventDTO,
    PlannerPreferencesDocument,
    PostDuePolicy,
    TaskCreate,
    TaskDTO,
    TaskUpdate,
    TimeKind,
    TodayDTO,
    as_utc,
    utc_now,
)
from adaptive_planner.persistence.models import Area, CalendarEvent, HistoryEvent, PlannerPreferences, Task


UNCATEGORIZED = "UNCATEGORIZED"


def _uuid(value: str) -> UUID:
    return UUID(value)


@overload
def _dt(value: datetime) -> datetime: ...


@overload
def _dt(value: None) -> None: ...


def _dt(value: datetime | None) -> datetime | None:
    return as_utc(value)


def _now_naive() -> datetime:
    """SQLite stores UTC timestamps without an offset; DTOs add UTC back on read."""
    return utc_now().replace(tzinfo=None)


def _area_dto(row: Area) -> AreaDTO:
    return AreaDTO(
        id=_uuid(row.id),
        system_key=row.system_key,
        name=row.name,
        kind=AreaKind(row.kind),
        default_post_due_policy=PostDuePolicy(row.default_post_due_policy),
        archived_at=_dt(row.archived_at),
        created_at=_dt(row.created_at),
        updated_at=_dt(row.updated_at),
    )


def _task_dto(row: Task) -> TaskDTO:
    return TaskDTO(
        id=_uuid(row.id),
        area_id=_uuid(row.area_id),
        title=row.title,
        description=row.description,
        earliest_start_at=_dt(row.earliest_start_at),
        deadline_kind=DeadlineKind(row.deadline_kind),
        due_date=row.due_date,
        due_at=_dt(row.due_at),
        estimated_remaining_seconds=row.estimated_remaining_seconds,
        priority=row.priority,
        can_split=bool(row.can_split),
        minimum_block_minutes_override=row.minimum_block_minutes_override,
        maximum_block_minutes_override=row.maximum_block_minutes_override,
        post_due_policy_override=PostDuePolicy(row.post_due_policy_override)
        if row.post_due_policy_override
        else None,
        completed_at=_dt(row.completed_at),
        archived_at=_dt(row.archived_at),
        created_at=_dt(row.created_at),
        updated_at=_dt(row.updated_at),
    )


def _event_dto(row: CalendarEvent) -> CalendarEventDTO:
    return CalendarEventDTO(
        id=_uuid(row.id),
        area_id=_uuid(row.area_id) if row.area_id else None,
        title=row.title,
        description=row.description,
        time_kind=TimeKind(row.time_kind),
        availability=Availability(row.availability),
        start_at=_dt(row.start_at),
        end_at=_dt(row.end_at),
        start_date=row.start_date,
        end_date=row.end_date,
        timezone_name=row.timezone_name,
        cancelled_at=_dt(row.cancelled_at),
        created_at=_dt(row.created_at),
        updated_at=_dt(row.updated_at),
        archived_at=_dt(row.archived_at),
    )


def _history_dto(row: HistoryEvent) -> HistoryEventDTO:
    return HistoryEventDTO(
        id=_uuid(row.id),
        operation_id=_uuid(row.operation_id),
        occurred_at=_dt(row.occurred_at),
        event_type=row.event_type,
        actor_type=row.actor_type,
        entity_type=row.entity_type,
        entity_id=_uuid(row.entity_id),
        payload_schema_version=row.payload_schema_version,
        before=row.before_json,
        after=row.after_json,
        metadata=row.metadata_json,
    )


def _record_history(
    session: Session,
    *,
    operation_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    before: Any = None,
    after: Any = None,
    metadata: dict[str, Any] | None = None,
    actor_type: str = "USER",
) -> None:
    def json_value(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    before_value = json_value(before)
    after_value = json_value(after)
    if isinstance(before_value, dict) and isinstance(after_value, dict):
        # History keeps meaningful sparse deltas for mutations. Identity and
        # row-maintenance timestamps are already represented by the event.
        ignored = {"id", "created_at", "updated_at"}
        changed = {
            key
            for key in before_value.keys() | after_value.keys()
            if key not in ignored and before_value.get(key) != after_value.get(key)
        }
        if not changed:
            return
        before_value = {key: before_value.get(key) for key in sorted(changed)}
        after_value = {key: after_value.get(key) for key in sorted(changed)}

    session.add(
        HistoryEvent(
            id=str(uuid4()),
            operation_id=str(operation_id),
            occurred_at=_now_naive(),
            event_type=event_type,
            actor_type=actor_type,
            entity_type=entity_type,
            entity_id=str(entity_id),
            payload_schema_version=1,
            before_json=before_value,
            after_json=after_value,
            metadata_json=metadata,
        )
    )


def _touch(row: Any, now: datetime | None = None) -> None:
    row.updated_at = (now or datetime.now(timezone.utc)).replace(tzinfo=None)


class CoreStore:
    """All v0.1 persistence behavior. Methods are called inside one DB session."""

    @staticmethod
    def ensure_uncategorized(session: Session) -> AreaDTO:
        row = session.scalar(select(Area).where(Area.system_key == UNCATEGORIZED))
        if row is None:
            row = Area(
                id=str(uuid4()),
                system_key=UNCATEGORIZED,
                name="None",
                kind=AreaKind.OTHER.value,
                default_post_due_policy=PostDuePolicy.ASK.value,
                created_at=_now_naive(),
                updated_at=_now_naive(),
            )
            session.add(row)
            session.flush()
        return _area_dto(row)

    @staticmethod
    def get_preferences(session: Session) -> PlannerPreferencesDocument:
        row = session.scalar(select(PlannerPreferences).limit(1))
        if row is None:
            document = PlannerPreferencesDocument()
            session.add(
                PlannerPreferences(
                    id=str(uuid4()),
                    format_version=document.format_version,
                    document_json=document.model_dump(mode="json"),
                    created_at=_now_naive(),
                    updated_at=_now_naive(),
                )
            )
            return document
        return PlannerPreferencesDocument.model_validate(row.document_json)

    @staticmethod
    def update_preferences(session: Session, document: PlannerPreferencesDocument) -> PlannerPreferencesDocument:
        row = session.scalar(select(PlannerPreferences).limit(1))
        before = PlannerPreferencesDocument.model_validate(row.document_json) if row else None
        if row is None:
            row = PlannerPreferences(id=str(uuid4()), created_at=_now_naive(), updated_at=_now_naive())
            session.add(row)
        row.format_version = document.format_version
        row.document_json = document.model_dump(mode="json")
        _touch(row)
        session.flush()
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="PREFERENCES_UPDATED",
            entity_type="PlannerPreferences",
            entity_id=_uuid(row.id),
            before=before,
            after=document,
        )
        return document

    @staticmethod
    def list_areas(session: Session, include_archived: bool = False) -> tuple[AreaDTO, ...]:
        statement = select(Area).order_by(Area.archived_at.is_not(None), Area.name)
        if not include_archived:
            statement = statement.where(Area.archived_at.is_(None))
        return tuple(_area_dto(row) for row in session.scalars(statement).all())

    @staticmethod
    def create_area(session: Session, data: AreaCreate) -> AreaDTO:
        if session.scalar(select(Area).where(Area.name == data.name, Area.archived_at.is_(None))):
            raise ValueError(f"an active Area named {data.name!r} already exists")
        now = _now_naive()
        row = Area(
            id=str(uuid4()),
            name=data.name,
            kind=data.kind.value,
            default_post_due_policy=data.default_post_due_policy.value,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        dto = _area_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="AREA_CREATED",
            entity_type="Area",
            entity_id=dto.id,
            after=dto,
        )
        return dto

    @staticmethod
    def rename_area(session: Session, area_id: UUID, name: str) -> AreaDTO:
        row = session.get(Area, str(area_id))
        if row is None:
            raise ValueError("Area not found")
        if row.system_key == UNCATEGORIZED:
            raise ValueError("the built-in None Area cannot be renamed")
        name = name.strip()
        if not name:
            raise ValueError("Area name cannot be empty")
        before = _area_dto(row)
        row.name = name
        _touch(row)
        session.flush()
        after = _area_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="AREA_UPDATED",
            entity_type="Area",
            entity_id=area_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def update_area(session: Session, area_id: UUID, data: AreaCreate) -> AreaDTO:
        row = session.get(Area, str(area_id))
        if row is None:
            raise ValueError("Area not found")
        if row.system_key == UNCATEGORIZED:
            raise ValueError("the built-in None Area cannot be edited")
        if session.scalar(select(Area).where(Area.name == data.name, Area.id != str(area_id), Area.archived_at.is_(None))):
            raise ValueError(f"an active Area named {data.name!r} already exists")
        before = _area_dto(row)
        row.name = data.name
        row.kind = data.kind.value
        row.default_post_due_policy = data.default_post_due_policy.value
        _touch(row)
        session.flush()
        after = _area_dto(row)
        if before != after:
            _record_history(session, operation_id=uuid4(), event_type="AREA_UPDATED", entity_type="Area", entity_id=area_id, before=before, after=after)
        return after

    @staticmethod
    def archive_area(
        session: Session,
        area_id: UUID,
        action: str = "area_only",
        destination_area_id: UUID | None = None,
    ) -> None:
        row = session.get(Area, str(area_id))
        if row is None:
            raise ValueError("Area not found")
        if row.system_key == UNCATEGORIZED:
            raise ValueError("the built-in None Area cannot be archived")
        incomplete = session.scalars(
            select(Task).where(Task.area_id == str(area_id), Task.completed_at.is_(None), Task.archived_at.is_(None))
        ).all()
        if action == "area_only" and incomplete:
            raise ValueError("Area has incomplete Tasks; choose archive_contents or move_contents")
        operation_id = uuid4()
        now = _now_naive()
        if action == "move_contents":
            if destination_area_id is None or destination_area_id == area_id:
                raise ValueError("a different destination Area is required")
            destination = session.get(Area, str(destination_area_id))
            if destination is None or destination.archived_at is not None:
                raise ValueError("destination Area is not active")
            for task in incomplete:
                before = _task_dto(task)
                task.area_id = str(destination_area_id)
                _touch(task, now)
                session.flush()
                _record_history(
                    session,
                    operation_id=operation_id,
                    event_type="TASK_MOVED_AREA",
                    entity_type="Task",
                    entity_id=_uuid(task.id),
                    before=before,
                    after=_task_dto(task),
                )
        elif action == "archive_contents":
            for task in incomplete:
                before = _task_dto(task)
                task.archived_at = now
                _touch(task, now)
                session.flush()
                _record_history(
                    session,
                    operation_id=operation_id,
                    event_type="TASK_ARCHIVED",
                    entity_type="Task",
                    entity_id=_uuid(task.id),
                    before=before,
                    after=_task_dto(task),
                )
        elif action != "area_only":
            raise ValueError("unknown Area archival action")
        before_area = _area_dto(row)
        row.archived_at = now
        _touch(row, now)
        session.flush()
        _record_history(
            session,
            operation_id=operation_id,
            event_type="AREA_ARCHIVED",
            entity_type="Area",
            entity_id=area_id,
            before=before_area,
            after=_area_dto(row),
        )

    @staticmethod
    def restore_area(session: Session, area_id: UUID) -> AreaDTO:
        row = session.get(Area, str(area_id))
        if row is None:
            raise ValueError("Area not found")
        if row.system_key == UNCATEGORIZED:
            raise ValueError("the built-in None Area is always active")
        if row.archived_at is None:
            raise ValueError("Area is already active")
        if session.scalar(
            select(Area).where(
                Area.name == row.name,
                Area.id != str(area_id),
                Area.archived_at.is_(None),
            )
        ):
            raise ValueError(
                f"an active Area named {row.name!r} already exists; rename one of the Areas before restoring"
            )

        before = _area_dto(row)
        row.archived_at = None
        _touch(row)
        session.flush()
        after = _area_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="AREA_RESTORED",
            entity_type="Area",
            entity_id=area_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def list_tasks(
        session: Session,
        *,
        inbox_only: bool = False,
        include_archived: bool = False,
        include_completed: bool = False,
    ) -> tuple[TaskDTO, ...]:
        statement = select(Task).order_by(Task.completed_at.is_not(None), Task.due_at.is_(None), Task.priority.desc(), Task.title)
        if not include_archived:
            statement = statement.where(Task.archived_at.is_(None))
        if not include_completed:
            statement = statement.where(Task.completed_at.is_(None))
        if inbox_only:
            statement = statement.where(Task.estimated_remaining_seconds.is_(None), Task.completed_at.is_(None))
        return tuple(_task_dto(row) for row in session.scalars(statement).all())

    @staticmethod
    def create_task(session: Session, data: TaskCreate) -> TaskDTO:
        area = session.get(Area, str(data.area_id))
        if area is None or area.archived_at is not None:
            raise ValueError("Task must belong to an active Area")
        now = _now_naive()
        row = Task(
            id=str(uuid4()),
            area_id=str(data.area_id),
            title=data.title,
            description=data.description,
            earliest_start_at=data.earliest_start_at.replace(tzinfo=None) if data.earliest_start_at else None,
            deadline_kind=data.deadline_kind.value,
            due_date=data.due_date,
            due_at=data.due_at.replace(tzinfo=None) if data.due_at else None,
            estimated_remaining_seconds=data.estimated_remaining_seconds,
            priority=data.priority,
            can_split=data.can_split,
            minimum_block_minutes_override=data.minimum_block_minutes_override,
            maximum_block_minutes_override=data.maximum_block_minutes_override,
            post_due_policy_override=data.post_due_policy_override.value if data.post_due_policy_override else None,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        dto = _task_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="TASK_CREATED",
            entity_type="Task",
            entity_id=dto.id,
            after=dto,
        )
        return dto

    @staticmethod
    def update_task(session: Session, task_id: UUID, changes: TaskUpdate) -> TaskDTO:
        row = session.get(Task, str(task_id))
        if row is None:
            raise ValueError("Task not found")
        current = _task_dto(row)
        allowed_fields = set(TaskCreate.model_fields)
        values = {key: value for key, value in current.model_dump().items() if key in allowed_fields}
        values.update(changes.model_dump(exclude_unset=True))
        merged = TaskCreate.model_validate(values)
        if merged.area_id != current.area_id:
            area = session.get(Area, str(merged.area_id))
            if area is None or area.archived_at is not None:
                raise ValueError("Task must belong to an active Area")
        before = current
        row.area_id = str(merged.area_id)
        row.title = merged.title
        row.description = merged.description
        row.earliest_start_at = merged.earliest_start_at.replace(tzinfo=None) if merged.earliest_start_at else None
        row.deadline_kind = merged.deadline_kind.value
        row.due_date = merged.due_date
        row.due_at = merged.due_at.replace(tzinfo=None) if merged.due_at else None
        row.estimated_remaining_seconds = merged.estimated_remaining_seconds
        row.priority = merged.priority
        row.can_split = merged.can_split
        row.minimum_block_minutes_override = merged.minimum_block_minutes_override
        row.maximum_block_minutes_override = merged.maximum_block_minutes_override
        row.post_due_policy_override = merged.post_due_policy_override.value if merged.post_due_policy_override else None
        _touch(row)
        session.flush()
        after = _task_dto(row)
        if before != after:
            _record_history(
                session,
                operation_id=uuid4(),
                event_type="TASK_UPDATED",
                entity_type="Task",
                entity_id=task_id,
                before=before,
                after=after,
            )
        return after

    @staticmethod
    def adjust_remaining_seconds(session: Session, task_id: UUID, seconds: int | None) -> TaskDTO:
        if seconds is not None and seconds < 0:
            raise ValueError("remaining estimate cannot be negative")
        return CoreStore.update_task(session, task_id, TaskUpdate(estimated_remaining_seconds=seconds))

    @staticmethod
    def adjust_remaining(session: Session, task_id: UUID, minutes: int | None) -> TaskDTO:
        """Backward-compatible minute API; storage is always integer seconds."""

        seconds = None if minutes is None else minutes * 60
        return CoreStore.adjust_remaining_seconds(session, task_id, seconds)

    @staticmethod
    def defer_task(session: Session, task_id: UUID, earliest_start_at: datetime | None) -> TaskDTO:
        return CoreStore.update_task(
            session,
            task_id,
            TaskUpdate(earliest_start_at=as_utc(earliest_start_at)),
        )

    @staticmethod
    def complete_task(session: Session, task_id: UUID) -> TaskDTO:
        row = session.get(Task, str(task_id))
        if row is None:
            raise ValueError("Task not found")
        if row.archived_at is not None:
            raise ValueError("archived Tasks cannot be completed")
        if row.completed_at is not None:
            return _task_dto(row)
        before = _task_dto(row)
        row.completed_at = _now_naive()
        _touch(row)
        session.flush()
        after = _task_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="TASK_COMPLETED",
            entity_type="Task",
            entity_id=task_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def reopen_task(session: Session, task_id: UUID) -> TaskDTO:
        row = session.get(Task, str(task_id))
        if row is None:
            raise ValueError("Task not found")
        if row.archived_at is not None:
            raise ValueError("restore the archived Task before reopening it")
        if row.completed_at is None:
            return _task_dto(row)
        before = _task_dto(row)
        row.completed_at = None
        _touch(row)
        session.flush()
        after = _task_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="TASK_REOPENED",
            entity_type="Task",
            entity_id=task_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def archive_task(session: Session, task_id: UUID) -> TaskDTO:
        row = session.get(Task, str(task_id))
        if row is None:
            raise ValueError("Task not found")
        if row.archived_at is not None:
            return _task_dto(row)
        before = _task_dto(row)
        row.archived_at = _now_naive()
        _touch(row)
        session.flush()
        after = _task_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="TASK_ARCHIVED",
            entity_type="Task",
            entity_id=task_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def restore_task(session: Session, task_id: UUID) -> TaskDTO:
        row = session.get(Task, str(task_id))
        if row is None:
            raise ValueError("Task not found")
        if row.archived_at is None:
            return _task_dto(row)
        area = session.get(Area, row.area_id)
        if area is None or area.archived_at is not None:
            raise ValueError("restore the Task's Area before restoring this Task")
        before = _task_dto(row)
        row.archived_at = None
        _touch(row)
        session.flush()
        after = _task_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="TASK_RESTORED",
            entity_type="Task",
            entity_id=task_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def list_events(
        session: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        include_cancelled: bool = False,
        include_archived: bool = False,
    ) -> tuple[CalendarEventDTO, ...]:
        statement = select(CalendarEvent).order_by(CalendarEvent.start_at, CalendarEvent.start_date, CalendarEvent.title)
        if not include_cancelled:
            statement = statement.where(CalendarEvent.cancelled_at.is_(None))
        if not include_archived:
            statement = statement.where(CalendarEvent.archived_at.is_(None))
        if start is not None and end is not None:
            start_naive = _dt(start).replace(tzinfo=None)
            end_naive = _dt(end).replace(tzinfo=None)
            statement = statement.where(
                or_(
                    and_(CalendarEvent.time_kind == TimeKind.TIMED.value, CalendarEvent.end_at > start_naive, CalendarEvent.start_at < end_naive),
                    and_(CalendarEvent.time_kind == TimeKind.ALL_DAY.value, CalendarEvent.end_date > start.date(), CalendarEvent.start_date < end.date()),
                )
            )
        return tuple(_event_dto(row) for row in session.scalars(statement).all())

    @staticmethod
    def get_event(session: Session, event_id: UUID) -> CalendarEventDTO:
        row = session.get(CalendarEvent, str(event_id))
        if row is None:
            raise ValueError("CalendarEvent not found")
        return _event_dto(row)

    @staticmethod
    def create_event(session: Session, data: CalendarEventCreate, actor_type: str = "USER") -> CalendarEventDTO:
        now = _now_naive()
        row = CalendarEvent(
            id=str(uuid4()),
            area_id=str(data.area_id) if data.area_id else None,
            title=data.title,
            description=data.description,
            time_kind=data.time_kind.value,
            availability=data.availability.value,
            start_at=data.start_at.replace(tzinfo=None) if data.start_at else None,
            end_at=data.end_at.replace(tzinfo=None) if data.end_at else None,
            start_date=data.start_date,
            end_date=data.end_date,
            timezone_name=data.timezone_name,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        dto = _event_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="CALENDAR_EVENT_CREATED",
            actor_type=actor_type,
            entity_type="CalendarEvent",
            entity_id=dto.id,
            after=dto,
        )
        return dto

    @staticmethod
    def update_event(
        session: Session,
        event_id: UUID,
        changes: CalendarEventUpdate,
    ) -> CalendarEventDTO:
        row = session.get(CalendarEvent, str(event_id))
        if row is None:
            raise ValueError("CalendarEvent not found")
        if row.cancelled_at is not None:
            raise ValueError("cancelled CalendarEvents cannot be edited")
        if row.archived_at is not None:
            raise ValueError("archived CalendarEvents cannot be edited")
        current = _event_dto(row)
        allowed_fields = set(CalendarEventCreate.model_fields)
        values = {key: value for key, value in current.model_dump().items() if key in allowed_fields}
        values.update(changes.model_dump(exclude_unset=True))
        merged = CalendarEventCreate.model_validate(values)
        if merged.area_id is not None:
            area = session.get(Area, str(merged.area_id))
            if area is None or area.archived_at is not None:
                raise ValueError("CalendarEvent Area must be active")

        row.area_id = str(merged.area_id) if merged.area_id else None
        row.title = merged.title
        row.description = merged.description
        row.time_kind = merged.time_kind.value
        row.availability = merged.availability.value
        row.start_at = merged.start_at.replace(tzinfo=None) if merged.start_at else None
        row.end_at = merged.end_at.replace(tzinfo=None) if merged.end_at else None
        row.start_date = merged.start_date
        row.end_date = merged.end_date
        row.timezone_name = merged.timezone_name
        _touch(row)
        session.flush()
        after = _event_dto(row)
        if current != after:
            _record_history(
                session,
                operation_id=uuid4(),
                event_type="CALENDAR_EVENT_UPDATED",
                entity_type="CalendarEvent",
                entity_id=event_id,
                before=current,
                after=after,
            )
        return after

    @staticmethod
    def cancel_event(session: Session, event_id: UUID) -> CalendarEventDTO:
        row = session.get(CalendarEvent, str(event_id))
        if row is None:
            raise ValueError("CalendarEvent not found")
        before = _event_dto(row)
        row.cancelled_at = _now_naive()
        _touch(row)
        session.flush()
        after = _event_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="CALENDAR_EVENT_CANCELLED",
            entity_type="CalendarEvent",
            entity_id=event_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def archive_event(session: Session, event_id: UUID) -> CalendarEventDTO:
        row = session.get(CalendarEvent, str(event_id))
        if row is None:
            raise ValueError("CalendarEvent not found")
        if row.cancelled_at is not None:
            raise ValueError("cancelled CalendarEvents cannot be archived")
        if row.archived_at is not None:
            return _event_dto(row)
        before = _event_dto(row)
        row.archived_at = _now_naive()
        _touch(row)
        session.flush()
        after = _event_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="CALENDAR_EVENT_ARCHIVED",
            entity_type="CalendarEvent",
            entity_id=event_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def restore_event(session: Session, event_id: UUID) -> CalendarEventDTO:
        row = session.get(CalendarEvent, str(event_id))
        if row is None:
            raise ValueError("CalendarEvent not found")
        if row.archived_at is None:
            raise ValueError("CalendarEvent is already active")
        if row.cancelled_at is not None:
            raise ValueError("cancelled CalendarEvents cannot be restored")
        before = _event_dto(row)
        row.archived_at = None
        _touch(row)
        session.flush()
        after = _event_dto(row)
        _record_history(
            session,
            operation_id=uuid4(),
            event_type="CALENDAR_EVENT_RESTORED",
            entity_type="CalendarEvent",
            entity_id=event_id,
            before=before,
            after=after,
        )
        return after

    @staticmethod
    def list_history(session: Session, limit: int = 100) -> tuple[HistoryEventDTO, ...]:
        rows = session.scalars(select(HistoryEvent).order_by(HistoryEvent.occurred_at.desc()).limit(limit)).all()
        return tuple(_history_dto(row) for row in rows)

    @staticmethod
    def today(session: Session, now: datetime | None = None) -> TodayDTO:
        preferences = CoreStore.get_preferences(session)
        current = (now or utc_now()).astimezone(ZoneInfo(preferences.timezone_name))
        day_start_local = datetime.combine(current.date(), time.min, tzinfo=current.tzinfo)
        day_end_local = day_start_local + timedelta(days=1)
        tasks = CoreStore.list_tasks(session)
        events = CoreStore.list_events(session, start=day_start_local, end=day_end_local)
        return TodayDTO(
            date=current.date(),
            tasks=tasks,
            events=events,
            inbox_count=sum(1 for task in tasks if task.estimated_remaining_seconds is None),
        )

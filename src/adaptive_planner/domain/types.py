"""Immutable domain DTOs and validation for the v0.1 feature set."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeadlineKind(StrEnum):
    NONE = "NONE"
    DATE = "DATE"
    DATETIME = "DATETIME"


class AreaKind(StrEnum):
    COURSE = "COURSE"
    WORK = "WORK"
    PROJECT = "PROJECT"
    ORGANIZATION = "ORGANIZATION"
    PERSONAL = "PERSONAL"
    OTHER = "OTHER"


class Availability(StrEnum):
    BUSY = "BUSY"
    FREE = "FREE"


class TimeKind(StrEnum):
    TIMED = "TIMED"
    ALL_DAY = "ALL_DAY"


class PostDuePolicy(StrEnum):
    ASK = "ASK"
    ALLOW = "ALLOW"
    FORBID = "FORBID"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PlannerPreferencesDocument(FrozenModel):
    """The singleton preference document, kept intentionally small in v0.1."""

    format_version: int = 1
    timezone_name: str = "UTC"
    scheduling: dict[str, Any] = Field(
        default_factory=lambda: {
            "sleep_windows": {},
            "work_windows": {},
            "protected_windows": [],
            "default_block_minutes": 60,
            "minimum_block_minutes": 20,
            "maximum_block_minutes": 90,
            "before_event_buffer_minutes": 10,
            "after_event_buffer_minutes": 10,
            "date_only_deadline_cutoff": "23:59",
        }
    )
    focus: dict[str, Any] = Field(default_factory=lambda: {"count_system_sleep_as_focus": False})
    automation: dict[str, Any] = Field(default_factory=lambda: {"llm_auto_mode": False})
    sync: dict[str, Any] = Field(default_factory=lambda: {"interval_minutes": 15})

    @field_validator("format_version")
    @classmethod
    def valid_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported preference format_version")
        return value

    @field_validator("timezone_name")
    @classmethod
    def nonempty_timezone(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("timezone_name cannot be empty")
        return value


class AreaDTO(FrozenModel):
    id: UUID
    system_key: str | None
    name: str
    kind: AreaKind
    default_post_due_policy: PostDuePolicy
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AreaCreate(FrozenModel):
    name: str = Field(min_length=1, max_length=200)
    kind: AreaKind = AreaKind.OTHER
    default_post_due_policy: PostDuePolicy = PostDuePolicy.ASK

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip()


class TaskDTO(FrozenModel):
    id: UUID
    area_id: UUID
    title: str
    description: str | None
    notes: str | None
    earliest_start_at: datetime | None
    deadline_kind: DeadlineKind
    due_date: date | None
    due_at: datetime | None
    estimated_remaining_minutes: int | None
    priority: int
    can_split: bool
    minimum_block_minutes_override: int | None
    maximum_block_minutes_override: int | None
    post_due_policy_override: PostDuePolicy | None
    completed_at: datetime | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskCreate(FrozenModel):
    area_id: UUID
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    notes: str | None = None
    earliest_start_at: datetime | None = None
    deadline_kind: DeadlineKind = DeadlineKind.NONE
    due_date: date | None = None
    due_at: datetime | None = None
    estimated_remaining_minutes: int | None = Field(default=None, ge=0)
    priority: int = Field(default=3, ge=1, le=5)
    can_split: bool = True
    minimum_block_minutes_override: int | None = Field(default=None, gt=0)
    maximum_block_minutes_override: int | None = Field(default=None, gt=0)
    post_due_policy_override: PostDuePolicy | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("earliest_start_at", "due_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None) -> datetime | None:
        return as_utc(value)

    @model_validator(mode="after")
    def validate_deadline_and_chunks(self) -> "TaskCreate":
        if self.deadline_kind is DeadlineKind.NONE and (self.due_date or self.due_at):
            raise ValueError("NONE deadline cannot include a due date or due_at")
        if self.deadline_kind is DeadlineKind.DATE and (self.due_date is None or self.due_at is not None):
            raise ValueError("DATE deadline requires due_date and no due_at")
        if self.deadline_kind is DeadlineKind.DATETIME and (self.due_at is None or self.due_date is not None):
            raise ValueError("DATETIME deadline requires due_at and no due_date")
        if self.maximum_block_minutes_override is not None and self.minimum_block_minutes_override is not None:
            if self.maximum_block_minutes_override < self.minimum_block_minutes_override:
                raise ValueError("maximum block size must be >= minimum block size")
        if not self.can_split and (
            self.minimum_block_minutes_override is not None or self.maximum_block_minutes_override is not None
        ):
            raise ValueError("non-splittable tasks cannot have block-size overrides")
        return self


class TaskUpdate(FrozenModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    notes: str | None = None
    area_id: UUID | None = None
    earliest_start_at: datetime | None = None
    deadline_kind: DeadlineKind | None = None
    due_date: date | None = None
    due_at: datetime | None = None
    estimated_remaining_minutes: int | None = Field(default=None, ge=0)
    priority: int | None = Field(default=None, ge=1, le=5)
    can_split: bool | None = None
    minimum_block_minutes_override: int | None = Field(default=None, gt=0)
    maximum_block_minutes_override: int | None = Field(default=None, gt=0)
    post_due_policy_override: PostDuePolicy | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("earliest_start_at", "due_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None) -> datetime | None:
        return as_utc(value)


class CalendarEventDTO(FrozenModel):
    id: UUID
    area_id: UUID | None
    title: str
    description: str | None
    time_kind: TimeKind
    availability: Availability
    start_at: datetime | None
    end_at: datetime | None
    start_date: date | None
    end_date: date | None
    timezone_name: str | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CalendarEventCreate(FrozenModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    area_id: UUID | None = None
    time_kind: TimeKind = TimeKind.TIMED
    availability: Availability = Availability.BUSY
    start_at: datetime | None = None
    end_at: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone_name: str | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None) -> datetime | None:
        return as_utc(value)

    @model_validator(mode="after")
    def validate_shape(self) -> "CalendarEventCreate":
        if self.time_kind is TimeKind.TIMED:
            if self.start_at is None or self.end_at is None or self.end_at <= self.start_at:
                raise ValueError("timed events require end_at > start_at")
            if self.start_date is not None or self.end_date is not None:
                raise ValueError("timed events cannot include all-day dates")
        else:
            if self.start_date is None or self.end_date is None or self.end_date <= self.start_date:
                raise ValueError("all-day events require end_date > start_date")
            if self.start_at is not None or self.end_at is not None:
                raise ValueError("all-day events cannot include timestamps")
        return self


class CalendarEventUpdate(FrozenModel):
    """Sparse editable CalendarEvent fields; explicit None clears a value."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    area_id: UUID | None = None
    time_kind: TimeKind | None = None
    availability: Availability | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    timezone_name: str | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None) -> datetime | None:
        return as_utc(value)


class HistoryEventDTO(FrozenModel):
    id: UUID
    operation_id: UUID
    occurred_at: datetime
    event_type: str
    actor_type: str
    entity_type: str
    entity_id: UUID
    payload_schema_version: int
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    metadata: dict[str, Any] | None


class TodayDTO(FrozenModel):
    date: date
    tasks: tuple[TaskDTO, ...]
    events: tuple[CalendarEventDTO, ...]
    inbox_count: int


def local_date_cutoff(day: date, cutoff: str, tz_name: str) -> datetime:
    """Resolve a date-only deadline for future scheduler use without changing its precision."""
    from zoneinfo import ZoneInfo

    hour, minute = (int(part) for part in cutoff.split(":", 1))
    return datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)

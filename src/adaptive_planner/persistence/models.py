"""SQLAlchemy models for the deliberately small v0.1 relational schema."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class PlannerPreferences(TimestampMixin, Base):
    __tablename__ = "planner_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    format_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    document_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Area(TimestampMixin, Base):
    __tablename__ = "areas"
    __table_args__ = (
        UniqueConstraint("system_key", name="uq_areas_system_key"),
        CheckConstraint(
            "system_key IS NULL OR system_key IN ('UNCATEGORIZED')",
            name="ck_areas_system_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    system_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="OTHER")
    default_post_due_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="ASK")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("estimated_remaining_seconds IS NULL OR estimated_remaining_seconds >= 0", name="ck_tasks_estimate"),
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_tasks_priority"),
        CheckConstraint(
            "(deadline_kind = 'NONE' AND due_date IS NULL AND due_at IS NULL) OR "
            "(deadline_kind = 'DATE' AND due_date IS NOT NULL AND due_at IS NULL) OR "
            "(deadline_kind = 'DATETIME' AND due_date IS NULL AND due_at IS NOT NULL)",
            name="ck_tasks_deadline_shape",
        ),
        CheckConstraint("minimum_block_minutes_override IS NULL OR minimum_block_minutes_override > 0", name="ck_tasks_min_block"),
        CheckConstraint("maximum_block_minutes_override IS NULL OR maximum_block_minutes_override > 0", name="ck_tasks_max_block"),
        CheckConstraint(
            "maximum_block_minutes_override IS NULL OR minimum_block_minutes_override IS NULL OR "
            "maximum_block_minutes_override >= minimum_block_minutes_override",
            name="ck_tasks_block_order",
        ),
        CheckConstraint(
            "can_split = 1 OR (minimum_block_minutes_override IS NULL AND maximum_block_minutes_override IS NULL)",
            name="ck_tasks_unsplittable_overrides",
        ),
        Index(
            "ix_tasks_due_at_active",
            "due_at",
            sqlite_where=text("completed_at IS NULL AND archived_at IS NULL AND due_at IS NOT NULL"),
        ),
        Index(
            "ix_tasks_due_date_active",
            "due_date",
            sqlite_where=text("completed_at IS NULL AND archived_at IS NULL AND due_date IS NOT NULL"),
        ),
        Index("ix_tasks_area_id", "area_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    area_id: Mapped[str] = mapped_column(String(36), ForeignKey("areas.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    earliest_start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deadline_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="NONE")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estimated_remaining_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    can_split: Mapped[bool] = mapped_column(nullable=False, default=True)
    minimum_block_minutes_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_block_minutes_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    post_due_policy_override: Mapped[str | None] = mapped_column(String(16), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CalendarEvent(TimestampMixin, Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        CheckConstraint(
            "(time_kind = 'TIMED' AND start_at IS NOT NULL AND end_at IS NOT NULL AND end_at > start_at "
            "AND start_date IS NULL AND end_date IS NULL) OR "
            "(time_kind = 'ALL_DAY' AND start_at IS NULL AND end_at IS NULL AND start_date IS NOT NULL "
            "AND end_date IS NOT NULL AND end_date > start_date)",
            name="ck_calendar_events_time_shape",
        ),
        Index(
            "ix_calendar_events_timed_active",
            "start_at",
            "end_at",
            sqlite_where=text("cancelled_at IS NULL AND time_kind = 'TIMED'"),
        ),
        Index(
            "ix_calendar_events_allday_active",
            "start_date",
            "end_date",
            sqlite_where=text("cancelled_at IS NULL AND time_kind = 'ALL_DAY'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    area_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("areas.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    availability: Mapped[str] = mapped_column(String(16), nullable=False, default="BUSY")
    start_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    timezone_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HistoryEvent(Base):
    __tablename__ = "history_events"
    __table_args__ = (
        Index("ix_history_events_operation_id", "operation_id"),
        Index("ix_history_events_entity", "entity_type", "entity_id", "occurred_at"),
        Index("ix_history_events_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    operation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="USER")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    before_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

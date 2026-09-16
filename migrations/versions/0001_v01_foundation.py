"""Create the phase-gated v0.1 foundation schema.

Keep this migration independent from the declarative ORM models.  Future
models must not silently appear in an old foundation migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_v01_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planner_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("format_version", sa.Integer(), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "areas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("system_key", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("default_post_due_policy", sa.String(length=16), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "system_key IS NULL OR system_key IN ('UNCATEGORIZED')",
            name="ck_areas_system_key",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("system_key", name="uq_areas_system_key"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("area_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("earliest_start_at", sa.DateTime(), nullable=True),
        sa.Column("deadline_kind", sa.String(length=16), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("estimated_remaining_minutes", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("can_split", sa.Boolean(), nullable=False),
        sa.Column("minimum_block_minutes_override", sa.Integer(), nullable=True),
        sa.Column("maximum_block_minutes_override", sa.Integer(), nullable=True),
        sa.Column("post_due_policy_override", sa.String(length=16), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "estimated_remaining_minutes IS NULL OR estimated_remaining_minutes >= 0",
            name="ck_tasks_estimate",
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="ck_tasks_priority"),
        sa.CheckConstraint(
            "(deadline_kind = 'NONE' AND due_date IS NULL AND due_at IS NULL) OR "
            "(deadline_kind = 'DATE' AND due_date IS NOT NULL AND due_at IS NULL) OR "
            "(deadline_kind = 'DATETIME' AND due_date IS NULL AND due_at IS NOT NULL)",
            name="ck_tasks_deadline_shape",
        ),
        sa.CheckConstraint(
            "minimum_block_minutes_override IS NULL OR minimum_block_minutes_override > 0",
            name="ck_tasks_min_block",
        ),
        sa.CheckConstraint(
            "maximum_block_minutes_override IS NULL OR maximum_block_minutes_override > 0",
            name="ck_tasks_max_block",
        ),
        sa.CheckConstraint(
            "maximum_block_minutes_override IS NULL OR minimum_block_minutes_override IS NULL OR "
            "maximum_block_minutes_override >= minimum_block_minutes_override",
            name="ck_tasks_block_order",
        ),
        sa.CheckConstraint(
            "can_split = 1 OR (minimum_block_minutes_override IS NULL AND maximum_block_minutes_override IS NULL)",
            name="ck_tasks_unsplittable_overrides",
        ),
        sa.ForeignKeyConstraint(["area_id"], ["areas.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_area_id", "tasks", ["area_id"])
    op.create_index(
        "ix_tasks_due_at_active",
        "tasks",
        ["due_at"],
        sqlite_where=sa.text("completed_at IS NULL AND archived_at IS NULL AND due_at IS NOT NULL"),
    )
    op.create_index(
        "ix_tasks_due_date_active",
        "tasks",
        ["due_date"],
        sqlite_where=sa.text("completed_at IS NULL AND archived_at IS NULL AND due_date IS NOT NULL"),
    )
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("area_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("time_kind", sa.String(length=16), nullable=False),
        sa.Column("availability", sa.String(length=16), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=True),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("timezone_name", sa.String(length=100), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(time_kind = 'TIMED' AND start_at IS NOT NULL AND end_at IS NOT NULL AND end_at > start_at "
            "AND start_date IS NULL AND end_date IS NULL) OR "
            "(time_kind = 'ALL_DAY' AND start_at IS NULL AND end_at IS NULL AND start_date IS NOT NULL "
            "AND end_date IS NOT NULL AND end_date > start_date)",
            name="ck_calendar_events_time_shape",
        ),
        sa.ForeignKeyConstraint(["area_id"], ["areas.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_calendar_events_timed_active",
        "calendar_events",
        ["start_at", "end_at"],
        sqlite_where=sa.text("cancelled_at IS NULL AND time_kind = 'TIMED'"),
    )
    op.create_index(
        "ix_calendar_events_allday_active",
        "calendar_events",
        ["start_date", "end_date"],
        sqlite_where=sa.text("cancelled_at IS NULL AND time_kind = 'ALL_DAY'"),
    )
    op.create_table(
        "history_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_history_events_operation_id", "history_events", ["operation_id"])
    op.create_index(
        "ix_history_events_entity",
        "history_events",
        ["entity_type", "entity_id", "occurred_at"],
    )
    op.create_index("ix_history_events_occurred_at", "history_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_history_events_occurred_at", table_name="history_events")
    op.drop_index("ix_history_events_entity", table_name="history_events")
    op.drop_index("ix_history_events_operation_id", table_name="history_events")
    op.drop_table("history_events")
    op.drop_index("ix_calendar_events_allday_active", table_name="calendar_events")
    op.drop_index("ix_calendar_events_timed_active", table_name="calendar_events")
    op.drop_table("calendar_events")
    op.drop_index("ix_tasks_due_date_active", table_name="tasks")
    op.drop_index("ix_tasks_due_at_active", table_name="tasks")
    op.drop_index("ix_tasks_area_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("areas")
    op.drop_table("planner_preferences")

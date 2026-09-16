"""Store task estimates as integer seconds.

Revision ID: 0002_task_estimates_in_seconds
Revises: 0001_v01_foundation
"""

from alembic import op
from sqlalchemy import inspect

revision = "0002_task_estimates_in_seconds"
down_revision = "0001_v01_foundation"
branch_labels = None
depends_on = None


def _task_columns() -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns("tasks")}


def upgrade() -> None:
    columns = _task_columns()
    # On a brand-new database, 0001 creates the current declarative schema and
    # the seconds column already exists. Existing v0.1 databases need both the
    # column rename and value conversion.
    if "estimated_remaining_minutes" not in columns:
        return
    op.execute("ALTER TABLE tasks RENAME COLUMN estimated_remaining_minutes TO estimated_remaining_seconds")
    op.execute(
        "UPDATE tasks SET estimated_remaining_seconds = estimated_remaining_seconds * 60 "
        "WHERE estimated_remaining_seconds IS NOT NULL"
    )


def downgrade() -> None:
    columns = _task_columns()
    if "estimated_remaining_seconds" not in columns:
        return
    op.execute(
        "UPDATE tasks SET estimated_remaining_seconds = CAST(estimated_remaining_seconds / 60 AS INTEGER) "
        "WHERE estimated_remaining_seconds IS NOT NULL"
    )
    op.execute("ALTER TABLE tasks RENAME COLUMN estimated_remaining_seconds TO estimated_remaining_minutes")

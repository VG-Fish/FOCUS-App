"""Merge task notes into descriptions and remove the duplicate field.

Revision ID: 0003_remove_task_notes
Revises: 0002_task_estimates_in_seconds
"""

from alembic import op
from sqlalchemy import inspect

revision = "0003_remove_task_notes"
down_revision = "0002_task_estimates_in_seconds"
branch_labels = None
depends_on = None


def _task_columns() -> set[str]:
    return {column["name"] for column in inspect(op.get_bind()).get_columns("tasks")}


def upgrade() -> None:
    if "notes" not in _task_columns():
        return
    op.execute(
        """
        UPDATE tasks
        SET description = CASE
            WHEN notes IS NULL OR TRIM(notes) = '' THEN description
            WHEN description IS NULL OR TRIM(description) = '' THEN notes
            ELSE RTRIM(description) || CHAR(10) || CHAR(10) || LTRIM(notes)
        END
        WHERE notes IS NOT NULL AND TRIM(notes) != ''
        """
    )
    op.execute("ALTER TABLE tasks DROP COLUMN notes")


def downgrade() -> None:
    if "notes" in _task_columns():
        return
    # Merged text cannot be separated reliably; downgrade restores the old
    # nullable shape while leaving the preserved text in description.
    op.execute("ALTER TABLE tasks ADD COLUMN notes TEXT")

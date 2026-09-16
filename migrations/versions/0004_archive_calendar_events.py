"""Add reversible archival for local calendar work blocks.

Revision ID: 0004_archive_calendar_events
Revises: 0003_remove_task_notes
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_archive_calendar_events"
down_revision = "0003_remove_task_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("calendar_events")}
    if "archived_at" not in columns:
        op.add_column("calendar_events", sa.Column("archived_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("calendar_events")}
    if "archived_at" in columns:
        op.drop_column("calendar_events", "archived_at")

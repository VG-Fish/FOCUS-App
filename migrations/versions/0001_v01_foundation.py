"""Create the phase-gated v0.1 foundation schema."""

from alembic import op

from adaptive_planner.persistence.models import Base

revision = "0001_v01_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The declarative model is intentionally limited to v0.1 tables. Later
    # milestones add models and migrations rather than pre-creating unused
    # schema here.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

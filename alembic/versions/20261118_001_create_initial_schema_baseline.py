"""Create the initial InsightFlow static schema baseline.

Revision ID: 20261118_001
Revises:
Create Date: 2026-11-18
"""

from typing import Sequence

from alembic import op

from app.database.connection import Base
from app.database import models  # noqa: F401


revision: str = "20261118_001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # checkfirst keeps this baseline safe for databases that already contain
    # the static application tables. Dynamic dataset tables are not managed here.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # A baseline stamp must never remove an existing production schema or data.
    # Future destructive reversals must be explicit, reviewed migrations.
    pass

"""Key workflow runs by the Temporal workflow executing them.

Revision ID: 9d0e1f2a3b44
Revises: 8c9d0e1f2a33
Create Date: 2026-09-27 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "9d0e1f2a3b44"
down_revision: str | None = "8c9d0e1f2a33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add workflow_run.temporal_workflow_id."""
    op.add_column(
        "workflow_run", sa.Column("temporal_workflow_id", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True)
    )
    op.create_index(op.f("ix_workflow_run_temporal_workflow_id"), "workflow_run", ["temporal_workflow_id"], unique=False)


def downgrade() -> None:
    """Drop workflow_run.temporal_workflow_id."""
    op.drop_index(op.f("ix_workflow_run_temporal_workflow_id"), table_name="workflow_run")
    op.drop_column("workflow_run", "temporal_workflow_id")

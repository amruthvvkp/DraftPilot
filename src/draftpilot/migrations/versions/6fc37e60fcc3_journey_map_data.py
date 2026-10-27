"""Journey map data: richer timeline events, shared story moments and narrative variants.

Existing events get ``intensity = 0`` and a ``chrono_index`` from their ``position``. Events that
share a scene or beat stay separate: the writer merges them into a moment, never the migration.

Revision ID: 6fc37e60fcc3
Revises: c3d4e5f6a7b8
Create Date: 2026-10-27 22:13:14
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "6fc37e60fcc3"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENT = "character_timeline_event"
_MOMENT_FK = "fk_character_timeline_event_moment_id"


def upgrade() -> None:
    """Create moments and variants, add the event fields and backfill them."""
    op.create_table(
        "story_moment",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False),
        sa.Column("chrono_index", sa.Float(), nullable=True),
        sa.Column("story_time", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("beat_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["beat_id"], ["story_beat.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scene.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_story_moment_project_id"), "story_moment", ["project_id"], unique=False)
    op.create_table(
        "narrative_variant",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("scene_ids", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_narrative_variant_project_id"), "narrative_variant", ["project_id"], unique=False)

    op.add_column(_EVENT, sa.Column("motivation", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False, server_default=""))
    op.add_column(_EVENT, sa.Column("history", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False, server_default=""))
    op.add_column(_EVENT, sa.Column("intensity", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(_EVENT, sa.Column("chrono_index", sa.Float(), nullable=True))
    op.add_column(_EVENT, sa.Column("moment_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_character_timeline_event_moment_id"), _EVENT, ["moment_id"], unique=False)
    op.create_foreign_key(_MOMENT_FK, _EVENT, "story_moment", ["moment_id"], ["id"], ondelete="SET NULL")
    for column in ("motivation", "history", "intensity"):
        op.alter_column(_EVENT, column, server_default=None)
    op.execute(sa.text(f"UPDATE {_EVENT} SET chrono_index = position"))


def downgrade() -> None:
    """Drop the event fields, then the variant and moment tables."""
    op.drop_constraint(_MOMENT_FK, _EVENT, type_="foreignkey")
    op.drop_index(op.f("ix_character_timeline_event_moment_id"), table_name=_EVENT)
    for column in ("moment_id", "chrono_index", "intensity", "history", "motivation"):
        op.drop_column(_EVENT, column)
    op.drop_index(op.f("ix_narrative_variant_project_id"), table_name="narrative_variant")
    op.drop_table("narrative_variant")
    op.drop_index(op.f("ix_story_moment_project_id"), table_name="story_moment")
    op.drop_table("story_moment")

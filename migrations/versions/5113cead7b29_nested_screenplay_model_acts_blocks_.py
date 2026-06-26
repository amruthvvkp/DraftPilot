"""nested screenplay model: acts, blocks, revisions, project metadata

Revision ID: 5113cead7b29
Revises: 121586f96c09
Create Date: 2026-06-26 10:02:31.807677

Reparents ``scene`` from ``screenplay`` onto a new ``act`` layer. Existing scenes are
backfilled under a default "Act One" per screenplay. ``scene.body`` is retained as the
rendered content cache; granular ``block`` rows are created lazily by the editor, so no
content is parsed (or lost) here.
"""

from collections.abc import Sequence
from datetime import datetime, timezone

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5113cead7b29"
down_revision: str | None = "121586f96c09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply the nested-screenplay schema with a default-act backfill."""
    # ``create_table`` auto-creates the enum types it uses (referencekind, blocktype).
    # ``screeningtype`` appears only in an ``add_column`` (which does not auto-create),
    # so create it explicitly first.
    screening_type = sa.Enum(
        "IMAX_1_43", "FLAT_1_85", "CINEMASCOPE_2_39", "WIDESCREEN_1_78",
        "ACADEMY_1_37", "OTHER",
        name="screeningtype",
    )
    screening_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "project_reference",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "FILM", "DIRECTOR", "SHORT", "ONLINE", "TV", "ACTING", "PLACE", "OTHER",
                name="referencekind",
            ),
            nullable=False,
        ),
        sa.Column("label", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_reference_project_id"), "project_reference", ["project_id"], unique=False
    )
    op.create_table(
        "act",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("screenplay_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["screenplay_id"], ["screenplay.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_act_position"), "act", ["position"], unique=False)
    op.create_index(op.f("ix_act_screenplay_id"), "act", ["screenplay_id"], unique=False)
    op.create_table(
        "block",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "element_type",
            sa.Enum(
                "ACTION", "CHARACTER", "DIALOGUE", "PARENTHETICAL", "TRANSITION", "LYRIC",
                "NOTE", "SECTION", "SYNOPSIS", "SHOT", "PAGE_BREAK",
                name="blocktype",
            ),
            nullable=False,
        ),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "character_extension", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True
        ),
        sa.Column("is_dual", sa.Boolean(), nullable=False),
        sa.Column("dual_group", sa.Integer(), nullable=True),
        sa.Column("translation", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "translation_lang", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("marks", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["scene_id"], ["scene.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_block_position"), "block", ["position"], unique=False)
    op.create_index(op.f("ix_block_scene_id"), "block", ["scene_id"], unique=False)
    op.create_table(
        "scene_revision",
        sa.Column("rev_number", sa.Integer(), nullable=False),
        sa.Column("message", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scene.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_scene_revision_rev_number"), "scene_revision", ["rev_number"], unique=False
    )
    op.create_index(
        op.f("ix_scene_revision_scene_id"), "scene_revision", ["scene_id"], unique=False
    )

    # Project metadata: text/enum columns are nullable; list columns default to "[]".
    op.add_column("project", sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("project", sa.Column("story_outline", sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column("project", sa.Column("visual_style", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=True))
    op.add_column("project", sa.Column("camera_type", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))
    op.add_column("project", sa.Column("screening_type", screening_type, nullable=True))
    op.add_column("project", sa.Column("artwork_url", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True))
    op.add_column("project", sa.Column("artwork_path", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True))
    op.add_column(
        "project",
        sa.Column("genres", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "project",
        sa.Column("languages", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.alter_column("project", "genres", server_default=None)
    op.alter_column("project", "languages", server_default=None)
    op.drop_column("project", "genre")

    # Reparent scenes: add nullable act_id, backfill a default act per screenplay, enforce.
    op.add_column("scene", sa.Column("act_id", sa.Integer(), nullable=True))
    _backfill_default_acts()
    op.alter_column("scene", "act_id", nullable=False)
    op.drop_index(op.f("ix_scene_screenplay_id"), table_name="scene")
    op.create_index(op.f("ix_scene_act_id"), "scene", ["act_id"], unique=False)
    op.drop_constraint(op.f("scene_screenplay_id_fkey"), "scene", type_="foreignkey")
    op.create_foreign_key("scene_act_id_fkey", "scene", "act", ["act_id"], ["id"])
    op.drop_column("scene", "screenplay_id")


def _backfill_default_acts() -> None:
    """Create one default act per screenplay and point its existing scenes at it."""
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    screenplay_ids = [
        row[0]
        for row in bind.execute(sa.text("SELECT DISTINCT screenplay_id FROM scene"))
    ]
    for screenplay_id in screenplay_ids:
        act_id = bind.execute(
            sa.text(
                "INSERT INTO act (created_at, updated_at, title, position, screenplay_id) "
                "VALUES (:now, :now, 'Act One', 0, :sid) RETURNING id"
            ),
            {"now": now, "sid": screenplay_id},
        ).scalar_one()
        bind.execute(
            sa.text("UPDATE scene SET act_id = :aid WHERE screenplay_id = :sid"),
            {"aid": act_id, "sid": screenplay_id},
        )


def downgrade() -> None:
    """Revert to the flat screenplay→scene schema, restoring scene.screenplay_id."""
    op.add_column("scene", sa.Column("screenplay_id", sa.INTEGER(), autoincrement=False, nullable=True))
    op.execute(
        "UPDATE scene SET screenplay_id = act.screenplay_id "
        "FROM act WHERE scene.act_id = act.id"
    )
    op.alter_column("scene", "screenplay_id", nullable=False)
    op.drop_constraint("scene_act_id_fkey", "scene", type_="foreignkey")
    op.create_foreign_key(
        op.f("scene_screenplay_id_fkey"), "scene", "screenplay", ["screenplay_id"], ["id"]
    )
    op.drop_index(op.f("ix_scene_act_id"), table_name="scene")
    op.create_index(op.f("ix_scene_screenplay_id"), "scene", ["screenplay_id"], unique=False)
    op.drop_column("scene", "act_id")

    op.add_column("project", sa.Column("genre", sa.VARCHAR(length=100), autoincrement=False, nullable=True))
    op.drop_column("project", "languages")
    op.drop_column("project", "genres")
    op.drop_column("project", "artwork_path")
    op.drop_column("project", "artwork_url")
    op.drop_column("project", "screening_type")
    op.drop_column("project", "camera_type")
    op.drop_column("project", "visual_style")
    op.drop_column("project", "story_outline")
    op.drop_column("project", "description")

    op.drop_index(op.f("ix_scene_revision_scene_id"), table_name="scene_revision")
    op.drop_index(op.f("ix_scene_revision_rev_number"), table_name="scene_revision")
    op.drop_table("scene_revision")
    op.drop_index(op.f("ix_block_scene_id"), table_name="block")
    op.drop_index(op.f("ix_block_position"), table_name="block")
    op.drop_table("block")
    op.drop_index(op.f("ix_act_screenplay_id"), table_name="act")
    op.drop_index(op.f("ix_act_position"), table_name="act")
    op.drop_table("act")
    op.drop_index(op.f("ix_project_reference_project_id"), table_name="project_reference")
    op.drop_table("project_reference")
    # Drop enum types created by the upgrade so a re-upgrade can recreate them cleanly.
    sa.Enum(name="screeningtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="blocktype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="referencekind").drop(op.get_bind(), checkfirst=True)

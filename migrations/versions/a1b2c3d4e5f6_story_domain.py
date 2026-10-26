"""Typed story domain: characters, relationships, timelines, locations, beats; storyline fields.

Backfills from the knowledge graph (Twin Keeper character/location nodes) and from outline
artifacts' beat metadata, so existing projects open with their cast and outline intact.

Revision ID: a1b2c3d4e5f6
Revises: 9d0e1f2a3b44
Create Date: 2026-10-26 10:00:00
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9d0e1f2a3b44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STORYLINE = (("premise", None), ("synopsis", None), ("theme", 1000), ("tone", 500))


def _create_tables() -> None:
    """Create the five story tables and their indexes."""
    op.create_table(
        "character",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("role", sqlmodel.sql.sqltypes.AutoString(length=40), nullable=False),
        sa.Column(
            "summary", sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False
        ),
        sa.Column("bio", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "want", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "need", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "motive", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "objective", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "flaw", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "arc_summary", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False
        ),
        sa.Column(
            "voice", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("cue", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
        sa.Column("dialogue_lines", sa.Integer(), nullable=False),
        sa.Column("scene_ids", sa.JSON(), nullable=False),
        sa.Column(
            "source", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False
        ),
        sa.Column("writer_edited", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_character_cue", "character", ["cue"])
    op.create_index("ix_character_project_id", "character", ["project_id"])
    op.create_table(
        "location",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False
        ),
        sa.Column(
            "visual_notes",
            sqlmodel.sql.sqltypes.AutoString(length=4000),
            nullable=False,
        ),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "heading_location",
            sqlmodel.sql.sqltypes.AutoString(length=300),
            nullable=True,
        ),
        sa.Column("int_ext", sa.JSON(), nullable=False),
        sa.Column("times", sa.JSON(), nullable=False),
        sa.Column("scene_ids", sa.JSON(), nullable=False),
        sa.Column(
            "source", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False
        ),
        sa.Column("writer_edited", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_heading_location", "location", ["heading_location"])
    op.create_index("ix_location_project_id", "location", ["project_id"])
    op.create_table(
        "story_beat",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "title", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False
        ),
        sa.Column(
            "summary", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False
        ),
        sa.Column(
            "beat_type", sqlmodel.sql.sqltypes.AutoString(length=60), nullable=False
        ),
        sa.Column(
            "status", sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False
        ),
        sa.Column("scene_ids", sa.JSON(), nullable=False),
        sa.Column("character_ids", sa.JSON(), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("act_id", sa.Integer(), nullable=True),
        sa.Column(
            "source", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["act_id"], ["act.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_story_beat_act_id", "story_beat", ["act_id"])
    op.create_index("ix_story_beat_project_id", "story_beat", ["project_id"])
    op.create_table(
        "character_relationship",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "relation", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False
        ),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source_character_id", sa.Integer(), nullable=False),
        sa.Column("target_character_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_character_id"], ["character.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_character_id"], ["character.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_relationship_project_id", "character_relationship", ["project_id"]
    )
    op.create_index(
        "ix_character_relationship_source_character_id",
        "character_relationship",
        ["source_character_id"],
    )
    op.create_index(
        "ix_character_relationship_target_character_id",
        "character_relationship",
        ["target_character_id"],
    )
    op.create_table(
        "character_timeline_event",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "story_time", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False
        ),
        sa.Column(
            "title", sqlmodel.sql.sqltypes.AutoString(length=300), nullable=False
        ),
        sa.Column(
            "description", sqlmodel.sql.sqltypes.AutoString(length=4000), nullable=False
        ),
        sa.Column(
            "objective", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "emotional_state",
            sqlmodel.sql.sqltypes.AutoString(length=300),
            nullable=False,
        ),
        sa.Column("character_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("beat_id", sa.Integer(), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["beat_id"], ["story_beat.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["character_id"], ["character.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scene.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_character_timeline_event_character_id",
        "character_timeline_event",
        ["character_id"],
    )
    op.create_index(
        "ix_character_timeline_event_project_id",
        "character_timeline_event",
        ["project_id"],
    )


def _backfill() -> None:
    """Copy graph characters/locations and outline beats into the new tables."""
    bind = op.get_bind()
    now = datetime.now(UTC)
    node = sa.table(
        "knowledge_node",
        sa.column("id", sa.Integer),
        sa.column("project_id", sa.Integer),
        sa.column("kind", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.String),
        sa.column("node_metadata", sa.JSON),
    )
    edge = sa.table(
        "knowledge_edge",
        sa.column("source_node_id", sa.Integer),
        sa.column("target_node_id", sa.Integer),
    )
    artifact = sa.table(
        "story_artifact",
        sa.column("project_id", sa.Integer),
        sa.column("kind", sa.String),
        sa.column("metadata", sa.JSON),
    )
    linked = {row[0] for row in bind.execute(sa.select(edge.c.source_node_id))} | {
        row[0] for row in bind.execute(sa.select(edge.c.target_node_id))
    }
    characters: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []
    migrated: list[int] = []
    rows = bind.execute(
        sa.select(node)
        .where(node.c.kind.in_(("character", "location")))
        .order_by(node.c.id)
    ).mappings()
    for position, row in enumerate(rows):
        meta = dict(row["node_metadata"] or {})
        twin = meta.get("source") == "twin_keeper"
        common = {
            "project_id": row["project_id"],
            "position": position,
            "notes": "",
            "scene_ids": [int(item) for item in meta.get("scene_ids") or []],
            "source": "twin" if twin else "writer",
            "writer_edited": bool(meta.get("writer_edited")) or not twin,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        if row["kind"] == "character":
            characters.append(
                {
                    **common,
                    "name": row["label"][:200],
                    "role": "supporting",
                    "summary": (row["description"] or "")[:1000],
                    "bio": "",
                    "want": "",
                    "need": "",
                    "motive": "",
                    "objective": "",
                    "flaw": "",
                    "arc_summary": "",
                    "voice": "",
                    "aliases": [],
                    "tags": [],
                    "cue": meta.get("cue"),
                    "dialogue_lines": int(meta.get("dialogue_lines") or 0),
                }
            )
        else:
            locations.append(
                {
                    **common,
                    "name": row["label"][:300],
                    "description": (row["description"] or "")[:4000],
                    "visual_notes": "",
                    "heading_location": meta.get("heading_location"),
                    "int_ext": list(meta.get("int_ext") or []),
                    "times": list(meta.get("times") or []),
                }
            )
        if row["id"] not in linked:
            migrated.append(row["id"])
    tables = {
        name: sa.Table(name, sa.MetaData(), autoload_with=bind)
        for name in ("character", "location", "story_beat")
    }
    if characters:
        op.bulk_insert(tables["character"], characters)
    if locations:
        op.bulk_insert(tables["location"], locations)
    if migrated:
        bind.execute(sa.delete(node).where(node.c.id.in_(migrated)))
    beats: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in bind.execute(
        sa.select(artifact).where(artifact.c.kind == "outline")
    ).mappings():
        if row["project_id"] in seen:
            continue
        items = (row["metadata"] or {}).get("beats") or []
        if not isinstance(items, list) or not items:
            continue
        seen.add(row["project_id"])
        for position, item in enumerate(items):
            if not isinstance(item, dict) or not item.get("title"):
                continue
            beats.append(
                {
                    "project_id": row["project_id"],
                    "act_id": None,
                    "position": position,
                    "title": str(item["title"])[:300],
                    "summary": str(item.get("summary") or "")[:4000],
                    "beat_type": "beat",
                    "status": "planned",
                    "scene_ids": [],
                    "character_ids": [],
                    "source": "writer",
                    "version": 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    if beats:
        op.bulk_insert(tables["story_beat"], beats)


def upgrade() -> None:
    """Add storyline columns, create the story tables, and backfill them."""
    for name, length in _STORYLINE:
        op.add_column(
            "project",
            sa.Column(
                name, sqlmodel.sql.sqltypes.AutoString(length=length), nullable=True
            ),
        )
    _create_tables()
    _backfill()


def downgrade() -> None:
    """Drop the story tables and storyline columns (backfilled graph nodes are not recreated)."""
    for name in (
        "character_timeline_event",
        "character_relationship",
        "story_beat",
        "location",
        "character",
    ):
        op.drop_table(name)
    for name, _length in reversed(_STORYLINE):
        op.drop_column("project", name)

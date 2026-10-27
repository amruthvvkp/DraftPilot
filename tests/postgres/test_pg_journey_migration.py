"""Opt-in tier: the journey map migration and its backfill against the local stack's Postgres (``-m postgres``)."""

import uuid

import psycopg
import pytest

from draftpilot.cli import migrate
from draftpilot.core.config import settings

pytestmark = pytest.mark.postgres

BEFORE = "c3d4e5f6a7b8"
JOURNEY = "6fc37e60fcc3"
_SEED = """
INSERT INTO project (created_at, updated_at, title, genres, languages, primary_language, version, project_instruction)
VALUES (now(), now(), 'Big Fish', '[]', '[]', 'en', 1, '');
INSERT INTO character (created_at, updated_at, name, role, summary, bio, want, need, motive, objective, flaw, arc_summary,
    voice, notes, aliases, tags, position, project_id, dialogue_lines, scene_ids, source, writer_edited, version)
VALUES (now(), now(), 'Will', 'lead', '', '', '', '', '', '', '', '', '', '', '[]', '[]', 0, 1, 0, '[]', 'writer', false, 1);
INSERT INTO character_timeline_event (created_at, updated_at, position, story_time, title, description, objective,
    emotional_state, character_id, project_id, version)
VALUES (now(), now(), 0, '1973', 'Born', '', '', '', 1, 1, 1), (now(), now(), 4, '1990', 'Leaves', '', '', '', 1, 1, 3);
"""


def _connect(db: str) -> psycopg.Connection:
    """Open an autocommit connection to one database on the configured server."""
    pg = settings.postgres
    return psycopg.connect(
        host=pg.host, port=pg.port, user=pg.user, password=pg.password.get_secret_value(), dbname=db, autocommit=True
    )


def test_journey_migration_backfills_and_downgrades(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing events get intensity 0 and chrono_index from position, no moments; downgrade removes it all."""
    name = f"journey_test_{uuid.uuid4().hex[:10]}"
    try:
        admin = _connect(settings.postgres.db)
    except psycopg.OperationalError as exc:
        pytest.fail(f"Local Postgres is not reachable ({exc}); start the stack or set POSTGRES__PORT")
    with admin:
        admin.execute(f'CREATE DATABASE "{name}"')
        try:
            monkeypatch.setattr(settings.postgres, "db", name)
            migrate(BEFORE)
            with _connect(name) as db:
                db.execute(_SEED)
            migrate(JOURNEY)
            with _connect(name) as db:
                rows = db.execute(
                    "SELECT title, chrono_index, intensity, motivation, history, moment_id, version"
                    " FROM character_timeline_event ORDER BY id"
                ).fetchall()
                assert rows == [("Born", 0.0, 0, "", "", None, 1), ("Leaves", 4.0, 0, "", "", None, 3)]
                assert db.execute("SELECT count(*) FROM story_moment").fetchone() == (0,)
                assert db.execute("SELECT count(*) FROM narrative_variant").fetchone() == (0,)
            migrate(BEFORE, downgrade=True)
            with _connect(name) as db:
                tables = db.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('story_moment', 'narrative_variant')"
                ).fetchone()
                columns = db.execute(
                    "SELECT count(*) FROM information_schema.columns WHERE table_name = 'character_timeline_event'"
                    " AND column_name IN ('motivation', 'history', 'intensity', 'chrono_index', 'moment_id')"
                ).fetchone()
                assert (tables, columns) == ((0,), (0,))
                assert db.execute("SELECT count(*) FROM character_timeline_event").fetchone() == (2,)
            migrate(JOURNEY)
        finally:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

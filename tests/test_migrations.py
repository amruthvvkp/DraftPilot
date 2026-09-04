"""Test the repository Alembic migration graph without a live database."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migrations_have_one_linear_head() -> None:
    """Keep schema history mergeable with exactly one current head."""
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    head = script.get_revision(heads[0])
    assert head is not None
    assert head.down_revision is not None

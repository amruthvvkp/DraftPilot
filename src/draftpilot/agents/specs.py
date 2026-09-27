"""Load declarative role specs (``specs/*.yaml``) for the writers' room."""

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

SPEC_DIR = Path(__file__).parent / "specs"


class RoleSpec(BaseModel):
    """Describe one room role: who it is, how it thinks, and how it samples."""

    key: str = Field(min_length=1, max_length=60)
    label: str
    description: str
    instructions: str = Field(min_length=20)
    temperature: float = Field(default=0.5, ge=0, le=2)
    max_requests: int = Field(default=12, ge=1, le=100)


@cache
def load_specs() -> dict[str, RoleSpec]:
    """Return every role spec keyed by role, validated once per process."""
    specs = [RoleSpec.model_validate(yaml.safe_load(path.read_text())) for path in sorted(SPEC_DIR.glob("*.yaml"))]
    return {spec.key: spec for spec in specs}


def role_spec(key: str) -> RoleSpec:
    """Return one role's spec, falling back to the story architect."""
    specs = load_specs()
    return specs.get(key) or specs["story_architect"]

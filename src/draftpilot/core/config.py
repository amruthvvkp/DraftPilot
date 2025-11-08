import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

if sys.version_info.minor < 11:
    import toml  # type: ignore
else:
    import tomllib as toml


__all__ = ["settings"]

_ROOT = Path(__file__).parent.parent.parent.parent
_PYPROJECT_TOML = _ROOT / "pyproject.toml"
_PYPROJECT_TOML_CONTENT = toml.loads(_PYPROJECT_TOML.read_text())


class Metadata(BaseSettings):
    name: str = _PYPROJECT_TOML_CONTENT["project"]["name"]
    version: str = _PYPROJECT_TOML_CONTENT["project"]["version"]
    description: str = _PYPROJECT_TOML_CONTENT["project"]["description"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="draftpilot_")

    metadata: Metadata = Metadata()


settings = Settings()

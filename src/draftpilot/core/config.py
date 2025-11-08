import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import tomllib as toml
except ImportError:
    import toml  # type: ignore


__all__ = ["settings"]

_ROOT = Path(__file__).parent.parent.parent.parent
_PYPROJECT_TOML = _ROOT / "pyproject.toml"

def get_pyproject_toml_content():
    if not hasattr(get_pyproject_toml_content, "_cache"):
        get_pyproject_toml_content._cache = toml.loads(_PYPROJECT_TOML.read_text())
    return get_pyproject_toml_content._cache

class Metadata(BaseSettings):
    @property
    def name(self) -> str:
        return get_pyproject_toml_content()["project"]["name"]

    @property
    def version(self) -> str:
        return get_pyproject_toml_content()["project"]["version"]

    @property
    def description(self) -> str:
        return get_pyproject_toml_content()["project"]["description"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="draftpilot_")

    metadata: Metadata = Metadata()


settings = Settings()

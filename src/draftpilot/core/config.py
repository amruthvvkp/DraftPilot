from functools import cached_property
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import tomllib as toml
except ImportError:
    import toml  # type: ignore


__all__ = ["settings"]

_ROOT = Path(__file__).parent.parent.parent.parent
_PYPROJECT_TOML = _ROOT / "pyproject.toml"


_pyproject_toml_cache = None


def get_pyproject_toml_content():
    global _pyproject_toml_cache
    if _pyproject_toml_cache is None:
        _pyproject_toml_cache = toml.loads(_PYPROJECT_TOML.read_text())
    return _pyproject_toml_cache


class Metadata(BaseSettings):
    @computed_field
    @cached_property
    def name(self) -> str:
        return get_pyproject_toml_content()["project"]["name"]

    @computed_field
    @cached_property
    def version(self) -> str:
        return get_pyproject_toml_content()["project"]["version"]

    @computed_field
    @cached_property
    def description(self) -> str:
        return get_pyproject_toml_content()["project"]["description"]


class OTELConfig(BaseSettings):
    exporter_otlp_endpoint: str = "http://localhost:4318"
    enabled: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")

    metadata: Metadata = Metadata()
    otel: OTELConfig = OTELConfig()


settings = Settings()

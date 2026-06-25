"""Application settings loaded from environment variables and pyproject.toml."""

from pathlib import Path
from typing import Any

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    import tomllib as toml
except ImportError:
    import toml  # type: ignore


__all__ = ["settings"]

_ROOT = Path(__file__).parent.parent.parent.parent
_PYPROJECT_TOML = _ROOT / "pyproject.toml"


_pyproject_toml_cache = None


def get_pyproject_toml_content() -> dict[str, Any]:
    """Return the parsed pyproject.toml, caching it after the first read."""
    global _pyproject_toml_cache
    if _pyproject_toml_cache is None:
        _pyproject_toml_cache = toml.loads(_PYPROJECT_TOML.read_text())
    return _pyproject_toml_cache


class Metadata(BaseSettings):
    """Project metadata sourced from pyproject.toml."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def name(self) -> str:
        """Return the project name."""
        return get_pyproject_toml_content()["project"]["name"]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def version(self) -> str:
        """Return the project version."""
        return get_pyproject_toml_content()["project"]["version"]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def description(self) -> str:
        """Return the project description."""
        return get_pyproject_toml_content()["project"]["description"]


class OTELConfig(BaseSettings):
    """OpenTelemetry export configuration."""

    model_config = SettingsConfigDict(env_prefix="OTEL__")

    exporter_otlp_endpoint: str = "http://localhost:4318"
    enabled: bool = False


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings and derived DSNs."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES__")

    host: str = "localhost"
    port: int = 5432
    user: str = "draftpilot"
    password: SecretStr = SecretStr("draftpilot")
    db: str = "draftpilot"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_dsn(self) -> str:
        """SQLAlchemy/asyncpg DSN used by the application engine."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_dsn(self) -> str:
        """Synchronous DSN used by Alembic migrations."""
        return (
            f"postgresql+psycopg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class RedisSettings(BaseSettings):
    """Redis connection settings for the cache client."""

    model_config = SettingsConfigDict(env_prefix="REDIS__")

    host: str = "localhost"
    port: int = 6379
    db: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        """Return the Redis connection URL."""
        return f"redis://{self.host}:{self.port}/{self.db}"


class QueueSettings(BaseSettings):
    """Redis target + queue name for the ARQ worker."""

    model_config = SettingsConfigDict(env_prefix="QUEUE__")

    host: str = "localhost"
    port: int = 6379
    db: int = 1
    queue_name: str = "draftpilot:queue"


class LLMSettings(BaseSettings):
    """Provider-agnostic LLM configuration.

    Supports self-hosted (Ollama, LM Studio, vLLM) or cloud providers. Safe
    defaults so the app boots without a live model; the analysis task degrades
    gracefully when no provider is reachable.
    """

    model_config = SettingsConfigDict(env_prefix="LLM__")

    provider: str = "openai"
    base_url: str | None = None
    api_key: SecretStr = SecretStr("")
    model: str = "gpt-4o-mini"
    enabled: bool = False


class UISettings(BaseSettings):
    """NiceGUI web interface settings."""

    model_config = SettingsConfigDict(env_prefix="UI__")

    host: str = "0.0.0.0"
    port: int = 8000
    storage_secret: SecretStr = SecretStr("change-me-in-production")
    title: str = "DraftPilot"
    reload: bool = False


class Settings(BaseSettings):
    """Top-level application settings aggregating every settings group."""

    model_config = SettingsConfigDict(env_nested_delimiter="__")

    metadata: Metadata = Metadata()
    otel: OTELConfig = OTELConfig()
    postgres: PostgresSettings = PostgresSettings()
    redis: RedisSettings = RedisSettings()
    queue: QueueSettings = QueueSettings()
    llm: LLMSettings = LLMSettings()
    ui: UISettings = UISettings()


settings = Settings()

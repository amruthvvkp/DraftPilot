"""Application settings loaded from environment variables and pyproject.toml."""

from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, computed_field
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


class SecretsSettings(BaseSettings):
    """Encryption configuration for credentials stored by DraftPilot."""

    model_config = SettingsConfigDict(env_prefix="SECRETS__")

    master_key: SecretStr = SecretStr("")


class MCPSettings(BaseSettings):
    """MCP transport authentication settings."""

    model_config = SettingsConfigDict(env_prefix="MCP__")

    auth_token: SecretStr = SecretStr("draftpilot-local-token")
    admin_token: SecretStr = SecretStr("draftpilot-local-admin-token")
    client_tokens: dict[str, SecretStr] = Field(default_factory=dict)
    stdio_client_id: str = Field(default="mcp-stdio", min_length=1, max_length=200)
    request_timeout_seconds: float = 10.0
    max_output_chars: int = 100_000


class RAGSettings(BaseSettings):
    """Local retrieval service configuration."""

    model_config = SettingsConfigDict(env_prefix="RAG__")

    auth_token: SecretStr = SecretStr("draftpilot-local-token")
    max_results: int = 8
    embedding_provider: str = "hash"
    database_path: Path = Path("/tmp/draftpilot-rag.sqlite3")
    service_url: str = "http://rag:8000"


class BackupSettings(BaseSettings):
    """Local backup storage configuration."""

    model_config = SettingsConfigDict(env_prefix="BACKUP__")

    root: Path = Path("/tmp/draftpilot-backups")


class MontySettings(BaseSettings):
    """Feature gate and resource limits for model-generated glue code."""

    model_config = SettingsConfigDict(env_prefix="MONTY__")

    enabled: bool = False
    max_code_chars: int = 20_000
    max_input_items: int = 100
    max_duration_seconds: float = 0.5
    max_output_chars: int = 20_000


class EvalSettings(BaseSettings):
    """Local LM Studio target for Tier 1 tests, Tier 2 evals, and the LLM judge.

    Every LLM-backed test and eval runs against local LM Studio. Empty model names
    mean "use the first model LM Studio reports as loaded".
    """

    model_config = SettingsConfigDict(env_prefix="EVAL__")

    base_url: str = "http://localhost:1234/v1"
    chat_model: str = ""
    judge_model: str = ""
    embedding_model: str = ""


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
    secrets: SecretsSettings = SecretsSettings()
    mcp: MCPSettings = MCPSettings()
    rag: RAGSettings = RAGSettings()
    backup: BackupSettings = BackupSettings()
    monty: MontySettings = MontySettings()
    eval: EvalSettings = EvalSettings()
    ui: UISettings = UISettings()


settings = Settings()

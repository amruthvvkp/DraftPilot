"""Application settings loaded from environment variables and pyproject.toml."""

from pathlib import Path
from typing import Any, Literal

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
    # Langfuse score API (writer feedback, proposal decisions, online checks). Empty keys disable scores.
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def langfuse_base_url(self) -> str:
        """Return the Langfuse base URL: explicit, or derived from its OTLP endpoint."""
        if self.langfuse_host:
            return self.langfuse_host.rstrip("/")
        return self.exporter_otlp_endpoint.split("/api/public/otel")[0].rstrip("/")


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
    """Provider-agnostic default LLM configuration (writers can add more profiles in Settings).

    The default is a local LM Studio server with ``model="auto"``, which uses the first
    model LM Studio reports as loaded. Agent features degrade with a clear error when no
    provider is reachable.
    """

    model_config = SettingsConfigDict(env_prefix="LLM__")

    provider: str = "lm_studio"
    base_url: str | None = None
    api_key: SecretStr = SecretStr("")
    model: str = "auto"
    enabled: bool = True
    # Private hosts trusted for model servers (local LM Studio/Ollama reached from containers).
    # Other private or link-local provider targets stay blocked to prevent SSRF.
    trusted_model_hosts: list[str] = Field(default_factory=lambda: ["host.docker.internal"])
    # Per model request; generous because local reasoning models can think for many minutes.
    request_timeout_seconds: float = Field(default=1200.0, gt=0)
    # Model reasoning: "auto" follows each role's spec, "on"/"off" force it for every role. Off is
    # several times faster on local reasoning models (e.g. Qwen in LM Studio).
    thinking: Literal["auto", "on", "off"] = "auto"


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
    approval_ttl_seconds: int = Field(default=900, gt=0)
    # Identity of DraftPilot's own in-app agents when they call this MCP server in-process.
    internal_client_id: str = Field(default="draftpilot-room", min_length=1, max_length=200)


class RAGSettings(BaseSettings):
    """Hybrid retrieval service configuration (vector + full-text, fused with RRF)."""

    model_config = SettingsConfigDict(env_prefix="RAG__")

    auth_token: SecretStr = SecretStr("draftpilot-local-token")
    max_results: int = 8
    service_url: str = "http://rag:8000"
    # Store: "postgres" (pgvector + tsvector; compose default) or "sqlite" (FTS5; local/tests).
    backend: str = "sqlite"
    database_url: SecretStr = SecretStr("postgresql://draftpilot:draftpilot@localhost:55432/draftpilot")
    database_path: Path = Path("/tmp/draftpilot-rag.sqlite3")
    # Embeddings: "lm_studio" (default), "openai_compatible", "hash" (offline), or "none" (lexical).
    embedding_provider: str = "lm_studio"
    embedding_model: str = "text-embedding-nomic-embed-text-v1.5"
    embedding_base_url: str = "http://localhost:1234/v1"
    embedding_api_key: SecretStr = SecretStr("")
    embedding_dimensions: int = Field(default=768, ge=8, le=4096)
    # nomic-embed-text needs task prefixes; clear them for models that do not.
    embedding_document_prefix: str = "search_document: "
    embedding_query_prefix: str = "search_query: "


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


class APISettings(BaseSettings):
    """REST API access control for the single-user studio.

    When ``token`` is set, every ``/api/v1`` route requires ``Authorization: Bearer <token>``
    or a signed session cookie obtained by submitting the token once. When it is empty the API
    is open, which is only appropriate on a loopback-bound development host.
    """

    model_config = SettingsConfigDict(env_prefix="API__")

    token: SecretStr = SecretStr("")
    session_max_age_seconds: int = Field(default=30 * 24 * 3600, gt=0)
    cookie_secure: bool = False


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


class WebSettings(BaseSettings):
    """Web process settings: the FastAPI API that also serves the React studio build."""

    model_config = SettingsConfigDict(env_prefix="WEB__")

    host: str = "0.0.0.0"
    port: int = 8000
    title: str = "DraftPilot"
    reload: bool = False
    # Built React studio served by the web process (``npm --prefix frontend run build``).
    frontend_dist: Path = _ROOT / "frontend" / "dist"


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
    api: APISettings = APISettings()
    web: WebSettings = WebSettings()


settings = Settings()

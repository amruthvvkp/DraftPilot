# Configuration

All configuration comes from the environment through one `settings` singleton
(`draftpilot.core.config`). Each settings group is a pydantic-settings `BaseSettings` class with its
own `env_prefix`, aggregated as a field on `Settings`, which also sets `env_nested_delimiter="__"`.
So `POSTGRES__HOST` sets `settings.postgres.host`. Bare names such as `HOST` or `USER` are never
read: every group is prefixed, so system variables cannot collide with settings. No `env_file` is
configured, so only real environment variables are read; `.env.example` documents them.

To add a group, subclass `BaseSettings` with a new `env_prefix` and add it as a field on `Settings`.

## Settings groups

Defaults below are the values in code. Secrets are `SecretStr`; list and dict fields are read from
JSON.

### `Metadata` (`settings.metadata`)

No environment variables. Computed from the installed `draftpilot-studio` distribution: `name`
(`"draftpilot"`), `version` (`"0+unknown"` when not installed) and `description`.

### `OTELConfig` — `OTEL__`

| Field | Type | Default |
|---|---|---|
| `exporter_otlp_endpoint` | `str` | `http://localhost:4318` |
| `enabled` | `bool` | `False` |

### `PostgresSettings` — `POSTGRES__`

| Field | Type | Default |
|---|---|---|
| `host` | `str` | `localhost` |
| `port` | `int` | `5432` |
| `user` | `str` | `draftpilot` |
| `password` | `SecretStr` | `draftpilot` |
| `db` | `str` | `draftpilot` |

Computed: `async_dsn` (`postgresql+asyncpg://…`, the application engine) and `sync_dsn`
(`postgresql+psycopg://…`, Alembic).

### `RedisSettings` — `REDIS__`

| Field | Type | Default |
|---|---|---|
| `host` | `str` | `localhost` |
| `port` | `int` | `6379` |
| `db` | `int` | `0` |

Computed: `url` (`redis://host:port/db`).

### `TemporalSettings` — `TEMPORAL__`

| Field | Type | Default |
|---|---|---|
| `host` | `str` | `localhost:7233` |
| `namespace` | `str` | `default` |
| `task_queue` | `str` | `draftpilot` |
| `model_timeout_seconds` | `int` (≥ 10) | `900` |

### `LLMSettings` — `LLM__`

| Field | Type | Default |
|---|---|---|
| `provider` | `str` | `lm_studio` |
| `base_url` | `str \| None` | `None` |
| `api_key` | `SecretStr` | empty |
| `model` | `str` | `auto` (the first model LM Studio reports as loaded) |
| `enabled` | `bool` | `True` |
| `trusted_model_hosts` | `list[str]` | `["host.docker.internal"]` |
| `request_timeout_seconds` | `float` (> 0) | `1200.0` |
| `thinking` | `"auto" \| "on" \| "off"` | `auto` |

### `SecretsSettings` — `SECRETS__`

| Field | Type | Default |
|---|---|---|
| `master_key` | `SecretStr` | empty |

### `MCPSettings` — `MCP__`

| Field | Type | Default |
|---|---|---|
| `auth_token` | `SecretStr` | `draftpilot-local-token` |
| `admin_token` | `SecretStr` | `draftpilot-local-admin-token` |
| `client_tokens` | `dict[str, SecretStr]` | `{}` |
| `stdio_client_id` | `str` (1–200 chars) | `mcp-stdio` |
| `request_timeout_seconds` | `float` | `10.0` |
| `max_output_chars` | `int` | `100000` |
| `approval_ttl_seconds` | `int` (> 0) | `900` |
| `internal_client_id` | `str` (1–200 chars) | `draftpilot-room` |

### `RAGSettings` — `RAG__`

| Field | Type | Default |
|---|---|---|
| `auth_token` | `SecretStr` | `draftpilot-local-token` |
| `max_results` | `int` | `8` |
| `service_url` | `str` | `http://rag:8000` |
| `backend` | `str` | `sqlite` (`postgres` in compose) |
| `database_url` | `SecretStr` | `postgresql://draftpilot:draftpilot@localhost:55432/draftpilot` |
| `database_path` | `Path` | `/tmp/draftpilot-rag.sqlite3` |
| `embedding_provider` | `str` | `lm_studio` (also `openai_compatible`, `hash`, `none`) |
| `embedding_model` | `str` | `text-embedding-nomic-embed-text-v1.5` |
| `embedding_base_url` | `str` | `http://localhost:1234/v1` |
| `embedding_api_key` | `SecretStr` | empty |
| `embedding_dimensions` | `int` (8–4096) | `768` |
| `embedding_document_prefix` | `str` | `search_document: ` |
| `embedding_query_prefix` | `str` | `search_query: ` |

### `BackupSettings` — `BACKUP__`

| Field | Type | Default |
|---|---|---|
| `root` | `Path` | `/tmp/draftpilot-backups` |

### `MontySettings` — `MONTY__`

| Field | Type | Default |
|---|---|---|
| `enabled` | `bool` | `False` |
| `max_code_chars` | `int` | `20000` |
| `max_input_items` | `int` | `100` |
| `max_duration_seconds` | `float` | `0.5` |
| `max_output_chars` | `int` | `20000` |

### `EvalSettings` — `EVAL__`

| Field | Type | Default |
|---|---|---|
| `base_url` | `str` | `http://localhost:1234/v1` |
| `chat_model` | `str` | empty (first loaded model) |
| `judge_model` | `str` | empty (first loaded model) |
| `embedding_model` | `str` | empty (first loaded model) |

### `APISettings` — `API__`

| Field | Type | Default |
|---|---|---|
| `token` | `SecretStr` | empty (API open; loopback development only) |
| `session_max_age_seconds` | `int` (> 0) | `2592000` (30 days) |
| `cookie_secure` | `bool` | `False` |

### `WebSettings` — `WEB__`

| Field | Type | Default |
|---|---|---|
| `host` | `str` | `0.0.0.0` |
| `port` | `int` | `8000` |
| `title` | `str` | `DraftPilot` |
| `reload` | `bool` | `False` |
| `frontend_dist` | `Path` | the packaged `draftpilot/studio` build, else the checkout's `frontend/dist` |
| `require_frontend` | `bool` | `False` |

## API

::: draftpilot.core.config

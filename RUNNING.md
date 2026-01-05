# Running DraftPilot

This document describes how to run the DraftPilot application and tests.

## Prerequisites

- Python 3.11+ with `uv` package manager installed
- Redis server (for NiceGUI state management)
- Docker and Docker Compose (for containerized deployment)

## 1. Running from Local CLI

### Start Redis (if not already running)

```bash
# Using Docker
docker run -d -p 6379:6379 redis:alpine

# Or using Homebrew (macOS)
brew services start redis

# Or using systemd (Linux)
sudo systemctl start redis
```

### Run the Application

```bash
# Option 1: Using the run script
./run_app.sh

# Option 2: Direct command
uv run uvicorn draftpilot.app.main:app --host 0.0.0.0 --port 8000 --reload

# Option 3: Using Python directly
uv run python -m draftpilot.app.main
```

The application will be available at:
- Main UI: http://localhost:8000
- FastMCP endpoint: http://localhost:8000/mcp
- FastAPI docs: http://localhost:8000/docs

### Environment Variables

You can configure the application using environment variables:

```bash
# Redis configuration
export DRAFTPILOT_REDIS_URL=redis://localhost:6379
export DRAFTPILOT_NICEGUI_REDIS_URL=redis://localhost:6379

# Logfire configuration
export DRAFTPILOT_LOGFIRE_ENABLED=true
export DRAFTPILOT_LOGFIRE_SERVICE_NAME=draftpilot
export DRAFTPILOT_LOGFIRE_OTEL_ENDPOINT=http://localhost:4318

# LLM Provider configuration
export DRAFTPILOT_LLM_PROVIDER=openai
export DRAFTPILOT_OPENAI_MODEL_NAME=gpt-4o-mini
export DRAFTPILOT_OPENAI_API_KEY=sk-...

# Or use a .env file
cp .env.example .env
# Edit .env with your settings
```

## 2. Running from Docker

### Build and Start Services

```bash
# Build and start all services
docker compose up --build

# Or run in detached mode
docker compose up -d --build

# View logs
docker compose logs -f ui

# Stop services
docker compose down
```

### Access the Application

- Main UI: http://localhost:9000
- FastMCP endpoint: http://localhost:9000/mcp
- Grafana UI: http://localhost:3000
- Redis: localhost:6379

### Docker Compose Services

- `ui`: DraftPilot application (port 9000)
- `redis`: Redis server for NiceGUI state (port 6379)
- `grafana`: Grafana LGTM for OTEL traces (port 3000)

### Accessing Host Services from Docker

When running in Docker but accessing services on your host machine (e.g., Ollama):

**Mac/Windows (Docker Desktop):**
- Use `host.docker.internal` to access host services
- Example: `DRAFTPILOT_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1`
- This is already configured in `compose.yaml` for Ollama

**Linux:**
- Use your host's IP address or `172.17.0.1` (default Docker bridge gateway)
- Or add `network_mode: host` to the service (not recommended for production)

**Environment Variables for Host Services:**
```bash
# Ollama on host machine
DRAFTPILOT_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1

# Other services on host
DRAFTPILOT_OPENAI_BASE_URL=http://host.docker.internal:8080/v1  # If using local proxy
```

## 3. Running Tests

### Run All Tests

```bash
# Option 1: Using the test script
./run_tests.sh

# Option 2: Direct command
uv run pytest tests/unit/ -v

# Option 3: With coverage
uv run pytest tests/unit/ -v --cov=src --cov-report=html
```

### Run Specific Test Suites

```bash
# Configuration tests
uv run pytest tests/unit/test_core_config.py -v

# Agent orchestrator tests
uv run pytest tests/unit/test_agents_orchestrator.py -v

# Logging tests
uv run pytest tests/unit/test_core_logging.py -v

# Application tests
uv run pytest tests/unit/test_app_main.py -v
```

### Test Requirements

Tests use mocks for external dependencies (Redis, Logfire, LLM APIs), so no external services are required for running tests.

## Troubleshooting

### Redis Connection Issues

If you see Redis connection errors:

```bash
# Check if Redis is running
redis-cli ping

# Should return: PONG

# If not running, start it:
docker run -d -p 6379:6379 redis:alpine
```

### Port Already in Use

If port 8000 is already in use:

```bash
# Change the port in the command
uv run uvicorn draftpilot.app.main:app --host 0.0.0.0 --port 8001

# Or set environment variable
export PORT=8001
```

### Import Errors

If you see import errors:

```bash
# Ensure dependencies are installed
uv sync

# Verify Python path
uv run python -c "import sys; print('\n'.join(sys.path))"
```

### Docker Build Issues

If Docker build fails:

```bash
# Clean build
docker compose build --no-cache

# Check Docker logs
docker compose logs ui

# Verify Dockerfile
cat Dockerfile
```

## Development

### Hot Reload

The application supports hot reload when using `--reload` flag:

```bash
uv run uvicorn draftpilot.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Debug Mode

Enable debug logging:

```bash
export DRAFTPILOT_LOGFIRE_ENABLED=true
export LOG_LEVEL=DEBUG
uv run uvicorn draftpilot.app.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug
```


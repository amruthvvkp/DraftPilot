"""Pytest configuration and fixtures."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient

__all__ = []


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_logfire():
    """Mock Logfire instance."""
    mock = MagicMock()
    mock.span = MagicMock(
        return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock())
    )
    mock.instrument_fastapi = MagicMock()
    return mock


@pytest.fixture
def test_app():
    """Create a test FastAPI app instance."""
    app = FastAPI()
    return app


@pytest.fixture
def test_client(test_app: FastAPI):
    """Create a test client for FastAPI app."""
    return TestClient(test_app)


@pytest.fixture
async def async_client(test_app: FastAPI):
    """Create an async test client for FastAPI app."""
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_fastmcp():
    """Mock FastMCP server instance."""
    mock = MagicMock()
    mock.http_app = MagicMock(return_value=MagicMock())
    mock.tool = MagicMock()
    return mock


@pytest.fixture
def env_override(monkeypatch):
    """Fixture to override environment variables."""

    def _set_env(key: str, value: str):
        monkeypatch.setenv(key, value)

    def _del_env(key: str):
        monkeypatch.delenv(key, raising=False)

    return _set_env, _del_env


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    """Reset environment variables before each test."""
    # Store original values
    original_env = {}
    for key in os.environ:
        if key.startswith("DRAFTPILOT_") or key.startswith("NICEGUI_"):
            original_env[key] = os.environ[key]

    # Clear test-related env vars
    for key in list(os.environ.keys()):
        if key.startswith("DRAFTPILOT_") or key.startswith("NICEGUI_"):
            monkeypatch.delenv(key, raising=False)

    yield

    # Restore original values
    for key, value in original_env.items():
        monkeypatch.setenv(key, value)

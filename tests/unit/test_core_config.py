"""Unit tests for configuration module."""

import os
from unittest.mock import patch

from draftpilot.core.config import Settings, settings


class TestSettings:
    """Test suite for Settings class."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        test_settings = Settings()
        assert test_settings.redis_url == "redis://localhost:6379"
        assert test_settings.nicegui_redis_url == "redis://localhost:6379"
        assert test_settings.logfire.enabled is True
        assert test_settings.logfire.service_name == "draftpilot"
        assert test_settings.logfire.otel_endpoint == "http://localhost:4318"
        assert test_settings.mcp_mount_path == "/mcp"

    def test_redis_url_parsing(self):
        """Test Redis URL parsing from environment variable."""
        with patch.dict(os.environ, {"DRAFTPILOT_REDIS_URL": "redis://test:6380"}):
            test_settings = Settings()
            assert test_settings.redis_url == "redis://test:6380"

    def test_logfire_settings(self):
        """Test Logfire settings from environment variables."""
        with patch.dict(
            os.environ,
            {
                "DRAFTPILOT_LOGFIRE_ENABLED": "false",
                "DRAFTPILOT_LOGFIRE_SERVICE_NAME": "test-service",
                "DRAFTPILOT_LOGFIRE_OTEL_ENDPOINT": "http://test:4318",
            },
        ):
            test_settings = Settings()
            assert test_settings.logfire.enabled is False
            assert test_settings.logfire.service_name == "test-service"
            assert test_settings.logfire.otel_endpoint == "http://test:4318"

    def test_mcp_mount_path(self):
        """Test MCP mount path setting."""
        with patch.dict(os.environ, {"DRAFTPILOT_MCP_MOUNT_PATH": "/custom/mcp"}):
            test_settings = Settings()
            assert test_settings.mcp_mount_path == "/custom/mcp"

    def test_nicegui_redis_url(self):
        """Test NiceGUI Redis URL setting."""
        with patch.dict(
            os.environ, {"DRAFTPILOT_NICEGUI_REDIS_URL": "redis://nicegui:6379"}
        ):
            test_settings = Settings()
            assert test_settings.nicegui_redis_url == "redis://nicegui:6379"

    def test_env_prefix_works(self):
        """Test that env_prefix works correctly with pydantic-settings."""
        with patch.dict(
            os.environ,
            {
                "DRAFTPILOT_REDIS_URL": "redis://env:6379",
                "DRAFTPILOT_LOGFIRE_ENABLED": "false",
            },
        ):
            test_settings = Settings()
            assert test_settings.redis_url == "redis://env:6379"
            assert test_settings.logfire.enabled is False

    def test_settings_singleton(self):
        """Test that settings is a singleton instance."""
        from draftpilot.core.config import settings as settings2

        assert settings is settings2

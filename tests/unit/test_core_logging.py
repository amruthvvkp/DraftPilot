"""Unit tests for logging module."""

from unittest.mock import MagicMock, patch

from draftpilot.core.logging import configure_logfire


class TestLogfireConfiguration:
    """Test suite for Logfire configuration."""

    @patch("draftpilot.core.logging.logfire")
    @patch("draftpilot.core.logging.settings")
    def test_configure_logfire_enabled(self, mock_settings, mock_logfire):
        """Test Logfire initialization when enabled."""
        mock_logfire_settings = MagicMock()
        mock_logfire_settings.enabled = True
        mock_logfire_settings.service_name = "test-service"
        mock_logfire_settings.otel_endpoint = "http://test:4318"
        mock_settings.logfire = mock_logfire_settings

        result = configure_logfire()

        mock_logfire.configure.assert_called_once_with(
            service_name="test-service",
            otel_endpoint="http://test:4318",
        )
        mock_logfire.instrument_fastapi.assert_called_once()
        assert result is mock_logfire

    @patch("draftpilot.core.logging.logfire")
    @patch("draftpilot.core.logging.settings")
    def test_configure_logfire_disabled(self, mock_settings, mock_logfire):
        """Test Logfire initialization when disabled."""
        mock_logfire_settings = MagicMock()
        mock_logfire_settings.enabled = False
        mock_settings.logfire = mock_logfire_settings

        result = configure_logfire()

        mock_logfire.configure.assert_not_called()
        mock_logfire.instrument_fastapi.assert_not_called()
        assert result is None

    @patch("draftpilot.core.logging.logfire")
    @patch("draftpilot.core.logging.settings")
    def test_otel_exporter_configuration(self, mock_settings, mock_logfire):
        """Test OTEL exporter configuration."""
        mock_logfire_settings = MagicMock()
        mock_logfire_settings.enabled = True
        mock_logfire_settings.service_name = "draftpilot"
        mock_logfire_settings.otel_endpoint = "http://grafana:4318"
        mock_settings.logfire = mock_logfire_settings

        configure_logfire()

        mock_logfire.configure.assert_called_once_with(
            service_name="draftpilot",
            otel_endpoint="http://grafana:4318",
        )

    @patch("draftpilot.core.logging.logfire")
    @patch("draftpilot.core.logging.settings")
    def test_fastapi_instrumentation(self, mock_settings, mock_logfire):
        """Test FastAPI instrumentation is called."""
        mock_logfire_settings = MagicMock()
        mock_logfire_settings.enabled = True
        mock_logfire_settings.service_name = "test"
        mock_logfire_settings.otel_endpoint = "http://test:4318"
        mock_settings.logfire = mock_logfire_settings

        configure_logfire()

        mock_logfire.instrument_fastapi.assert_called_once()

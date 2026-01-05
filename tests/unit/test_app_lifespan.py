"""Unit tests for lifespan context manager."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from draftpilot.app.lifespan import lifespan


class TestLifespan:
    """Test suite for lifespan context manager."""

    @pytest.mark.asyncio
    @patch("draftpilot.app.lifespan.configure_logfire")
    async def test_lifespan_startup(self, mock_configure_logfire):
        """Test lifespan context manager startup."""
        mock_logfire = MagicMock()
        mock_logfire.span = MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=None),
                __exit__=MagicMock(return_value=None),
            )
        )
        mock_configure_logfire.return_value = mock_logfire

        app = FastAPI()

        async with lifespan(app):
            # Verify Logfire was configured
            mock_configure_logfire.assert_called_once()
            # Verify span was created for startup
            assert mock_logfire.span.called

    @pytest.mark.asyncio
    @patch("draftpilot.app.lifespan.configure_logfire")
    async def test_lifespan_shutdown(self, mock_configure_logfire):
        """Test lifespan context manager shutdown."""
        mock_logfire = MagicMock()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=None)
        mock_span.__exit__ = MagicMock(return_value=None)
        mock_logfire.span = MagicMock(return_value=mock_span)
        mock_configure_logfire.return_value = mock_logfire

        app = FastAPI()

        async with lifespan(app):
            pass

        # Verify shutdown span was created
        assert mock_logfire.span.call_count >= 2  # Startup and shutdown

    @pytest.mark.asyncio
    @patch("draftpilot.app.lifespan.configure_logfire")
    async def test_lifespan_logfire_disabled(self, mock_configure_logfire):
        """Test lifespan when Logfire is disabled."""
        mock_configure_logfire.return_value = None

        app = FastAPI()

        async with lifespan(app):
            # Should not raise any errors
            pass

        mock_configure_logfire.assert_called_once()

    @pytest.mark.asyncio
    @patch("draftpilot.app.lifespan.configure_logfire")
    async def test_lifespan_yields_control(self, mock_configure_logfire):
        """Test that lifespan yields control to the application."""
        mock_configure_logfire.return_value = None

        app = FastAPI()
        yielded = False

        async with lifespan(app):
            yielded = True

        assert yielded is True

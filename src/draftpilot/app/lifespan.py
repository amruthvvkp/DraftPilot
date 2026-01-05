"""Lifespan handlers for FastAPI application."""

import logfire
from fastapi import FastAPI

from draftpilot.core.config import settings

__all__ = ["setup_lifespan_handlers"]


def setup_lifespan_handlers(app: FastAPI) -> None:
    """Setup startup and shutdown handlers for the FastAPI application.

    Since NiceGUI already has its own lifespan, we add our handlers
    to NiceGUI's existing lifespan using on_startup and on_shutdown.

    :param app: FastAPI application instance (NiceGUI's app).
    """
    logfire_instance = logfire if settings.logfire.enabled else None

    @app.on_startup
    async def startup_handler():
        """Handle application startup."""
        if logfire_instance:
            with logfire_instance.span("application.startup"):
                # Initialize database connection pool (placeholder)
                # Initialize vector store client (placeholder)
                pass
        else:
            # Initialize resources even if Logfire is disabled
            # Initialize database connection pool (placeholder)
            # Initialize vector store client (placeholder)
            pass

    @app.on_shutdown
    async def shutdown_handler():
        """Handle application shutdown."""
        if logfire_instance:
            with logfire_instance.span("application.shutdown"):
                # Cleanup database connections
                # Cleanup vector store clients
                pass
        else:
            # Cleanup resources even if Logfire is disabled
            # Cleanup database connections
            # Cleanup vector store clients
            pass

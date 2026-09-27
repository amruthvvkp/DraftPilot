"""Run the DraftPilot web process: ``python -m draftpilot.api``."""

import uvicorn

from draftpilot.core.config import settings


def main() -> None:
    """Serve the application factory with uvicorn (the factory configures telemetry)."""
    uvicorn.run(
        "draftpilot.api.app:create_app",
        factory=True,
        host=settings.web.host,
        port=settings.web.port,
        reload=settings.web.reload,
        reload_dirs=["src"] if settings.web.reload else None,
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()

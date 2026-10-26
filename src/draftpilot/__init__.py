"""DraftPilot: an open-source, agentic screenplay and story-development studio."""

import os

# Telemetry is opt-in (OTEL__ENABLED); without it Logfire should stay quiet, installed or not.
os.environ.setdefault("LOGFIRE_IGNORE_NO_CONFIG", "1")


def main() -> None:
    """Run the ``draftpilot`` command line."""
    from draftpilot.cli import main as cli

    cli()

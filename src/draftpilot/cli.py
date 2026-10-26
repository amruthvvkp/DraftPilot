"""The ``draftpilot`` command: serve the studio, run the worker, migrate, and serve MCP or RAG.

    draftpilot serve            # API + studio on WEB__HOST:WEB__PORT
    draftpilot worker           # Temporal worker (jobs, runs, the writers' room, chat)
    draftpilot migrate          # alembic upgrade head (migrations ship inside the package)
    draftpilot mcp [--http]     # MCP server over stdio (default) or Streamable HTTP
    draftpilot rag              # the retrieval service
    draftpilot version

Configuration comes from the environment (``POSTGRES__``, ``REDIS__``, ``TEMPORAL__``, ``LLM__``,
``WEB__``, ``MCP__``, ``RAG__`` ...), exactly as in the Docker images.
"""

import argparse
import asyncio
from importlib import metadata, resources
from pathlib import Path


def version() -> str:
    """Return the installed DraftPilot version."""
    try:
        return metadata.version("draftpilot-studio")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def migrations_dir() -> Path:
    """Return the Alembic migrations directory shipped with the package."""
    return Path(str(resources.files("draftpilot") / "migrations"))


def migrate(revision: str = "head", *, downgrade: bool = False) -> None:
    """Upgrade (or downgrade) the database schema with the packaged migrations."""
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", str(migrations_dir()))
    (command.downgrade if downgrade else command.upgrade)(config, revision)


def serve(host: str | None, port: int | None, reload: bool) -> None:
    """Serve the API and the studio with uvicorn."""
    from draftpilot.api.__main__ import main
    from draftpilot.core.config import settings

    if host:
        settings.web.host = host
    if port:
        settings.web.port = port
    settings.web.reload = reload or settings.web.reload
    main()


def worker() -> None:
    """Run the Temporal worker until interrupted."""
    from draftpilot.worker.__main__ import main

    asyncio.run(main())


def mcp(http: bool, host: str, port: int) -> None:
    """Serve the MCP server over stdio, or Streamable HTTP with ``--http``."""
    from draftpilot.mcp.server import mcp as server

    if http:
        server.run(transport="http", host=host, port=port, show_banner=False)
    else:
        server.run(transport="stdio", show_banner=False)


def rag(host: str, port: int) -> None:
    """Serve the retrieval service."""
    import uvicorn

    uvicorn.run("draftpilot.rag_service:app", host=host, port=port, proxy_headers=True)


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    root = argparse.ArgumentParser(prog="draftpilot", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root.add_argument("--version", action="version", version=f"draftpilot {version()}")
    commands = root.add_subparsers(dest="command", required=True)
    serve_cmd = commands.add_parser("serve", help="serve the API and the studio")
    serve_cmd.add_argument("--host")
    serve_cmd.add_argument("--port", type=int)
    serve_cmd.add_argument("--reload", action="store_true", help="reload on source changes (development)")
    commands.add_parser("worker", help="run the Temporal worker")
    migrate_cmd = commands.add_parser("migrate", help="apply database migrations")
    migrate_cmd.add_argument("revision", nargs="?", default="head")
    migrate_cmd.add_argument("--downgrade", action="store_true", help="downgrade to REVISION instead")
    mcp_cmd = commands.add_parser("mcp", help="serve the MCP server")
    mcp_cmd.add_argument("--http", action="store_true", help="serve Streamable HTTP instead of stdio")
    mcp_cmd.add_argument("--host", default="0.0.0.0")
    mcp_cmd.add_argument("--port", type=int, default=8000)
    rag_cmd = commands.add_parser("rag", help="serve the retrieval service")
    rag_cmd.add_argument("--host", default="0.0.0.0")
    rag_cmd.add_argument("--port", type=int, default=8000)
    commands.add_parser("version", help="print the version")
    return root


def main(argv: list[str] | None = None) -> None:
    """Run one ``draftpilot`` command."""
    args = parser().parse_args(argv)
    if args.command == "serve":
        serve(args.host, args.port, args.reload)
    elif args.command == "worker":
        worker()
    elif args.command == "migrate":
        migrate(args.revision, downgrade=args.downgrade)
        print(f"database {'downgraded' if args.downgrade else 'migrated'} to {args.revision}")
    elif args.command == "mcp":
        mcp(args.http, args.host, args.port)
    elif args.command == "rag":
        rag(args.host, args.port)
    else:
        print(version())


if __name__ == "__main__":
    main()

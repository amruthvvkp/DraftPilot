"""The ``draftpilot-mcp`` command: serve DraftPilot over MCP, trust clients, and print client config.

    draftpilot-mcp                         # serve over stdio (the default; what MCP clients launch)
    draftpilot-mcp serve --http            # serve Streamable HTTP
    draftpilot-mcp trust CLIENT_ID         # grant a client every capability on every project
    draftpilot-mcp revoke CLIENT_ID        # remove a client's grants
    draftpilot-mcp config claude-code      # print how to connect a client
    draftpilot-mcp tools                   # list tools, prompts and resources
"""

import argparse
import asyncio
import json
import shlex
from importlib import metadata

CLIENTS = ("claude-code", "claude-desktop", "cursor", "http")


def _version() -> str:
    """Return the installed draftpilot-mcp version."""
    try:
        return metadata.version("draftpilot-mcp")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def serve(http: bool, host: str, port: int) -> None:
    """Run the server over stdio, or Streamable HTTP."""
    from draftpilot.mcp.server import mcp

    if http:
        mcp.run(transport="http", host=host, port=port, show_banner=False)
    else:
        mcp.run(transport="stdio", show_banner=False)


async def trust(client_id: str, name: str, project_id: int | None, capabilities: list[str]) -> list[str]:
    """Register a client (if new) and grant it capabilities on one project or installation-wide."""
    from sqlmodel import select

    from draftpilot.core.capabilities import capability_catalog
    from draftpilot.core.db import session_scope
    from draftpilot.crud import mcp_access
    from draftpilot.models import MCPClient, MCPGrant

    catalog = [item.name for item in capability_catalog()]
    wanted = catalog if not capabilities or capabilities == ["*"] else capabilities
    unknown = sorted(set(wanted) - set(catalog))
    if unknown:
        raise SystemExit(f"unknown capabilities: {', '.join(unknown)}")
    async with session_scope() as session:
        client = (await session.exec(select(MCPClient).where(MCPClient.client_id == client_id))).first()
        if client is None:
            client = MCPClient(client_id=client_id, name=name or client_id)
            session.add(client)
            await session.flush()
        held = {grant.capability for grant in await mcp_access.list_grants(session, project_id, client_id) if grant.project_id == project_id}
        session.add_all(
            [MCPGrant(client_id=client.id or 0, project_id=project_id, capability=item) for item in wanted if item not in held]
        )
        await session.commit()
    return wanted


async def revoke(client_id: str, project_id: int | None) -> int:
    """Remove a client's grants (on one project, or all of them)."""
    from sqlmodel import col, delete, select

    from draftpilot.core.db import session_scope
    from draftpilot.models import MCPClient, MCPGrant

    async with session_scope() as session:
        client = (await session.exec(select(MCPClient).where(MCPClient.client_id == client_id))).first()
        if client is None:
            return 0
        query = delete(MCPGrant).where(col(MCPGrant.client_id) == client.id)
        if project_id is not None:
            query = query.where(col(MCPGrant.project_id) == project_id)
        result = await session.exec(query)  # type: ignore[call-overload]
        await session.commit()
        return int(result.rowcount or 0)


def client_config(client: str, url: str, token: str) -> str:
    """Return the snippet that connects one MCP client to DraftPilot."""
    if client == "claude-code":
        return "claude mcp add draftpilot -- uvx draftpilot-mcp"
    if client == "http":
        return f"claude mcp add --transport http draftpilot {url} --header {shlex.quote('Authorization: Bearer ' + token)}"
    entry = {"command": "uvx", "args": ["draftpilot-mcp"], "env": {"POSTGRES__HOST": "localhost", "POSTGRES__PORT": "55432"}}
    return json.dumps({"mcpServers": {"draftpilot": entry}}, indent=2)


async def catalogue() -> dict[str, list[str]]:
    """List the server's tools, prompts and resource templates."""
    from draftpilot.mcp.server import mcp

    tools = await mcp.list_tools()
    prompts = await mcp.list_prompts()
    templates = await mcp.list_resource_templates()
    resources = await mcp.list_resources()
    return {
        "tools": [f"{tool.name}: {(tool.description or '').splitlines()[0]}" for tool in tools],
        "prompts": [prompt.name for prompt in prompts],
        "resources": [str(item.uri) for item in resources] + [str(item.uri_template) for item in templates],
    }


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    root = argparse.ArgumentParser(prog="draftpilot-mcp", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root.add_argument("--version", action="version", version=f"draftpilot-mcp {_version()}")
    commands = root.add_subparsers(dest="command")
    serve_cmd = commands.add_parser("serve", help="serve over stdio (default) or Streamable HTTP")
    serve_cmd.add_argument("--http", action="store_true")
    serve_cmd.add_argument("--host", default="0.0.0.0")
    serve_cmd.add_argument("--port", type=int, default=8000)
    trust_cmd = commands.add_parser("trust", help="grant a client capabilities")
    trust_cmd.add_argument("client_id")
    trust_cmd.add_argument("--name", default="")
    trust_cmd.add_argument("--project", type=int, help="one project (default: installation-wide)")
    trust_cmd.add_argument("--capability", action="append", default=[], help="repeatable; default: every capability")
    revoke_cmd = commands.add_parser("revoke", help="remove a client's grants")
    revoke_cmd.add_argument("client_id")
    revoke_cmd.add_argument("--project", type=int)
    config_cmd = commands.add_parser("config", help="print how to connect a client")
    config_cmd.add_argument("client", choices=CLIENTS)
    config_cmd.add_argument("--url", default="http://localhost:9001/mcp")
    config_cmd.add_argument("--token", default="draftpilot-local-token")
    commands.add_parser("tools", help="list tools, prompts and resources")
    return root


def main(argv: list[str] | None = None) -> None:
    """Run one ``draftpilot-mcp`` command (serving over stdio when none is given)."""
    args = parser().parse_args(argv)
    if args.command in (None, "serve"):
        serve(getattr(args, "http", False), getattr(args, "host", "0.0.0.0"), getattr(args, "port", 8000))
    elif args.command == "trust":
        granted = asyncio.run(trust(args.client_id, args.name, args.project, args.capability))
        scope = f"project {args.project}" if args.project else "every project"
        print(f"{args.client_id} may now use {len(granted)} capabilities on {scope}.")
    elif args.command == "revoke":
        print(f"removed {asyncio.run(revoke(args.client_id, args.project))} grants")
    elif args.command == "config":
        print(client_config(args.client, args.url, args.token))
    else:
        print(json.dumps(asyncio.run(catalogue()), indent=2))


if __name__ == "__main__":
    main()

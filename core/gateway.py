"""Heimdall gateway: MCP tools at /mcp and the model proxy at /model, one process on port 8080.

It replaced B's earlier stand-in gateway and keeps its URLs and log lines, so
agent configs don't change. Every tool call goes through the guard
(core/firewall/guard.py): identity, permissions, policy, one event.

Run with `python -m core.gateway`.
"""

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from core.firewall.config import GatewaySettings, load_settings
from core.firewall.guard import Guard
from core.firewall.session import Sessions
from core.firewall.tools import files
from core.proxy.model_route import make_model_route


def build_gateway(
    settings: GatewaySettings,
    transport: httpx.AsyncBaseTransport | None = None,
    sessions: Sessions | None = None,
) -> FastMCP:
    """Create the gateway app.

    transport: only for tests, to fake the model provider.
    sessions: only for tests, to look at or change session state.
    """
    mcp = FastMCP(
        "heimdall-gateway",
        host="0.0.0.0",
        port=8080,
        streamable_http_path="/mcp",
        # No MCP sessions: each call stands alone and names its agent by header.
        stateless_http=True,
        # Agents reach us as http://gateway:8080 on the internal network, which the default Host check rejects.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    guard = Guard(settings, sessions or Sessions())

    # Tool names use underscores: the Claude API rejects dots in tool names.
    # Tools are async so an approval wait does not block other calls.
    # structured_output=False: otherwise the SDK sends a second, JSON copy of every
    # result and agents show the model the text twice.
    # The docstrings are what the model reads, so they say how paths work.
    @mcp.tool(structured_output=False)
    async def files_list(ctx: Context, folder: str = "") -> str:
        """List what you may read. With no folder: your folders, each with its label and
        whether you may write to it. With a folder name (or "<folder>/<subfolder>"): the files
        in it, as paths to pass to files_read."""

        def work(run, target):
            return files.list_files(target) if target else files.list_folders(run.permissions)

        return await guard.run(ctx, "files_list", folder or None, work)

    @mcp.tool(structured_output=False)
    async def files_read(path: str, ctx: Context) -> str:
        """Read a text or PDF file. `path` is "<folder>/<path inside it>", as files_list shows it."""
        return await guard.run(ctx, "files_read", path, lambda run, target: files.read_file(target))

    @mcp.tool(structured_output=False)
    async def files_write(path: str, text: str, ctx: Context) -> str:
        """Create or replace a text file. `path` is "<folder>/<file name>"; the folder must be writable."""

        def work(run, target):
            files.write_file(target, text)
            return f"Wrote {len(text)} characters to {path}."

        return await guard.run(ctx, "files_write", path, work)

    # The model proxy shares the MCP server's HTTP app and port.
    mcp.custom_route("/model/{path:path}", methods=["GET", "POST"])(make_model_route(settings, transport))
    return mcp


if __name__ == "__main__":
    build_gateway(load_settings()).run(transport="streamable-http")

"""Heimdall gateway: MCP tools at /mcp and the model proxy at /model, one process on port 8080.

It replaces B's stand-in (agents/gateway/server.py) with the same URLs and log
lines, so agent configs don't change. Tools still return canned text; Step 1 adds
real files behind the policy guard.

Run with `python -m core.gateway`.
"""

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from core.firewall import core_client
from core.firewall.config import GatewaySettings, load_settings
from core.proxy.model_route import make_model_route

# Made-up content. The placeholder shows agents what redacted data looks like.
CANNED_FILES = {"notes.txt": "Canned text from the Heimdall gateway. Contact: {{EMAIL_1}}"}


def caller(ctx: Context, settings: GatewaySettings, tool: str) -> str:
    """The agent named by the bearer key on this MCP call.

    Fail closed: no HTTP request, no key or an unknown key raises, so the tool
    never runs. FastMCP turns the error into an error result for the agent.
    """
    try:
        headers = ctx.request_context.request.headers
    except (ValueError, AttributeError):
        headers = {}
    key = headers.get("authorization", "").removeprefix("Bearer ").strip()
    agent = settings.fake_keys.get(key)
    if agent is None:
        core_client.emit("tool_denied", tool=tool, reason="missing or unknown fake key")
        raise PermissionError("Heimdall: unknown agent")
    return agent


def build_gateway(settings: GatewaySettings, transport: httpx.AsyncBaseTransport | None = None) -> FastMCP:
    """Create the gateway app. transport: only for tests, to fake the model provider."""
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

    # Tool names use underscores: the Claude API rejects dots in tool names.
    # Tools are async so a later approval wait does not block other calls.
    # structured_output=False: otherwise the SDK sends a second, JSON copy of every
    # result and agents show the model the file text twice.
    @mcp.tool(structured_output=False)
    async def files_read(path: str, ctx: Context) -> str:
        """Read a file from the user's allowed folders."""
        core_client.emit("tool_call", agent=caller(ctx, settings, "files_read"), tool="files_read", path=path)
        return CANNED_FILES.get(path, f"(no file named {path})")

    @mcp.tool(structured_output=False)
    async def files_list(ctx: Context) -> list[str]:
        """List files in the user's allowed folders."""
        core_client.emit("tool_call", agent=caller(ctx, settings, "files_list"), tool="files_list")
        return list(CANNED_FILES)

    # The model proxy shares the MCP server's HTTP app and port.
    mcp.custom_route("/model/{path:path}", methods=["GET", "POST"])(make_model_route(settings, transport))
    return mcp


if __name__ == "__main__":
    build_gateway(load_settings()).run(transport="streamable-http")

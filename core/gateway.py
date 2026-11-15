"""Heimdall gateway: MCP tools at /mcp and the model proxy at /model, one process on port 8080.

It replaces B's images/fake-gateway/server.py with the same URLs, so OpenClaw's
config does not change. Step 0 tools return canned text; Step 1 adds real files
behind the policy guard.

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


def caller(ctx: Context, settings: GatewaySettings) -> str:
    """The agent named by the bearer key on this MCP call, or "unknown".

    Step 0 only records it. From Step 1 an unknown caller is denied.
    """
    try:
        headers = ctx.request_context.request.headers
    except (ValueError, AttributeError):
        # No HTTP request behind this call (an in-process call in tests).
        return "unknown"
    key = headers.get("authorization", "").removeprefix("Bearer ").strip()
    return settings.fake_keys.get(key, "unknown")


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
    @mcp.tool()
    async def files_read(path: str, ctx: Context) -> str:
        """Read a file from the user's allowed folders."""
        core_client.emit("tool_call", agent=caller(ctx, settings), tool="files_read", path=path)
        return CANNED_FILES.get(path, f"(no file named {path})")

    @mcp.tool()
    async def files_list(ctx: Context) -> list[str]:
        """List files in the user's allowed folders."""
        core_client.emit("tool_call", agent=caller(ctx, settings), tool="files_list")
        return list(CANNED_FILES)

    # The model proxy shares the MCP server's HTTP app and port.
    mcp.custom_route("/model/{path:path}", methods=["GET", "POST"])(make_model_route(settings, transport))
    return mcp


if __name__ == "__main__":
    build_gateway(load_settings()).run(transport="streamable-http")

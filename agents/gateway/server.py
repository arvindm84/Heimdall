"""Stand-in for the firewall's MCP tool server (A builds the real one).

Serves canned file tools on port 8000 at /mcp. Agents identify themselves
with their fake key as a bearer token, the same way A's gateway expects.
"""

import json

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

FAKE_KEY_PREFIX = "sk-fake-"
FAKE_FILES = {"notes.txt": "Canned text from the fake gateway. Contact: {{EMAIL_1}}"}

mcp = FastMCP(
    "heimdall-fake-gateway",
    host="0.0.0.0",
    port=8000,
    streamable_http_path="/mcp",
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def log(kind: str, **fields) -> None:
    print(json.dumps({"kind": kind, **fields}), flush=True)


def agent_key(ctx: Context) -> str:
    """The calling agent's fake key. Unknown callers are refused (fail closed)."""
    header = ctx.request_context.request.headers.get("authorization", "")
    key = header.removeprefix("Bearer ")
    if not key.startswith(FAKE_KEY_PREFIX):
        log("tool_denied", reason="no fake key on the tool call")
        raise PermissionError("unknown agent")
    return key


@mcp.tool()
def files_read(path: str, ctx: Context) -> str:
    """Read a file from the user's allowed folders."""
    log("tool_call", agent=agent_key(ctx), tool="files_read", path=path)
    return FAKE_FILES.get(path, f"(fake gateway has no file named {path})")


@mcp.tool()
def files_list(ctx: Context) -> list[str]:
    """List files in the user's allowed folders."""
    log("tool_call", agent=agent_key(ctx), tool="files_list")
    return list(FAKE_FILES)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

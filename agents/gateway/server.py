"""Stand-in for the firewall's gateway (A builds the real one in core/gateway.py).

One process on port 8080, the same shape as A's: MCP tools at /mcp and the model
proxy at /model/{path}. Agents carry only a fake key; the real key is added here.
A's gateway cannot serve Gemini yet, so this one stays the default until it can.
"""

import json
import os

import httpx
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

# "openclaw:sk-fake-openclaw-01,hermes:sk-fake-hermes-01" -> {fake key: agent}. Same setting as A's gateway.
FAKE_KEYS = {
    key.strip(): agent.strip()
    for agent, key in (item.split(":", 1) for item in os.environ.get("HEIMDALL_FAKE_KEYS", "").split(",") if ":" in item)
}
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
FORWARDED_HEADERS = ("anthropic-version", "anthropic-beta")
FAKE_FILES = {"notes.txt": "Canned text from the fake gateway. Contact: {{EMAIL_1}}"}

mcp = FastMCP(
    "heimdall-fake-gateway",
    host="0.0.0.0",
    port=8080,
    streamable_http_path="/mcp",
    stateless_http=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def log(kind: str, **fields) -> None:
    print(json.dumps({"kind": kind, **fields}), flush=True)


def caller(ctx: Context) -> str:
    """The agent named by the fake key on this tool call. Unknown callers are refused (fail closed)."""
    header = ctx.request_context.request.headers.get("authorization", "")
    agent = FAKE_KEYS.get(header.removeprefix("Bearer ").strip())
    if agent is None:
        log("tool_denied", reason="missing or unknown fake key")
        raise PermissionError("unknown agent")
    return agent


@mcp.tool()
async def files_read(path: str, ctx: Context) -> str:
    """Read a file from the user's allowed folders."""
    log("tool_call", agent=caller(ctx), tool="files_read", path=path)
    return FAKE_FILES.get(path, f"(fake gateway has no file named {path})")


@mcp.tool()
async def files_list(ctx: Context) -> list[str]:
    """List files in the user's allowed folders."""
    log("tool_call", agent=caller(ctx), tool="files_list")
    return list(FAKE_FILES)


def upstream_for(path: str) -> tuple[str, dict[str, str]] | None:
    """Provider URL and the header carrying the real key, chosen by the API the agent speaks."""
    if path.endswith("chat/completions"):  # OpenAI style: Gemini
        return GEMINI_URL, {"authorization": f"Bearer {os.environ.get('GEMINI_API_KEY', '')}"}
    if path.endswith("messages"):  # Anthropic style
        return f"https://api.anthropic.com/{path}", {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", "")}
    return None


def tools_offered(body: dict) -> list[str]:
    """Tool names in an Anthropic style or OpenAI style request."""
    return [tool.get("name") or tool.get("function", {}).get("name") for tool in body.get("tools") or []]


def sign_tool_calls(body: dict) -> dict:
    """Gemini rejects a replayed tool call without its thought signature, and OpenClaw drops it.

    Google documents this placeholder for clients that cannot keep the real signature.
    """
    for message in body.get("messages") or []:
        for call in (message.get("tool_calls") or []) if isinstance(message, dict) else []:
            google = call.setdefault("extra_content", {}).setdefault("google", {})
            google.setdefault("thought_signature", "skip_thought_signature_validator")
    return body


@mcp.custom_route("/model/{path:path}", methods=["GET", "POST"])
async def model(request: Request):
    path = request.path_params["path"]
    key = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    agent = FAKE_KEYS.get(key)
    if agent is None:
        log("model_blocked", path=path, reason="missing or unknown fake key")
        return JSONResponse({"error": "Heimdall: unknown key"}, status_code=401)
    upstream = upstream_for(path)
    if request.method != "POST" or upstream is None:
        log("model_other", agent=agent, method=request.method, path=path)
        return JSONResponse({"data": []})
    raw = await request.body()
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        log("model_blocked", agent=agent, path=path, reason="body is not a JSON object")
        return JSONResponse({"error": "Heimdall: body must be a JSON object"}, status_code=400)
    log("model_call", agent=agent, api_key=key, model=body.get("model"), tools_offered=tools_offered(body))
    if path.endswith("chat/completions"):
        raw = json.dumps(sign_tool_calls(body)).encode()
    url, headers = upstream
    if not any(value.removeprefix("Bearer ") for value in headers.values()):
        log("model_blocked", agent=agent, path=path, reason="no real key for this provider is set in the gateway")
        return JSONResponse({"error": "Heimdall: no real key for this provider"}, status_code=502)
    headers.update({name: request.headers[name] for name in FORWARDED_HEADERS if name in request.headers})
    headers["content-type"] = "application/json"
    client = httpx.AsyncClient(timeout=300)
    try:
        reply = await client.send(client.build_request("POST", url, headers=headers, content=raw), stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        log("model_upstream_error", agent=agent, url=url, reason=type(error).__name__)
        return JSONResponse({"error": "Heimdall: model provider unreachable"}, status_code=502)
    log("model_forwarded", agent=agent, url=url, model=body.get("model"), status=reply.status_code)
    if reply.status_code >= 400:
        # Provider errors are small: log the start so a failed chat can be explained.
        error = await reply.aread()
        await client.aclose()
        log("model_error", agent=agent, status=reply.status_code, body=error.decode(errors="replace")[:500])
        return Response(error, status_code=reply.status_code, media_type=reply.headers.get("content-type"))

    async def chunks():
        try:
            async for chunk in reply.aiter_bytes():
                yield chunk
        finally:
            await reply.aclose()
            await client.aclose()

    return StreamingResponse(chunks(), status_code=reply.status_code, media_type=reply.headers.get("content-type"))


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

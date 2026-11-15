"""Stand-in for the firewall's gateway (A builds the real one in core/gateway.py).

One process on port 8080, the same shape as A's: MCP tools at /mcp and the model
proxy at /model/{path}. Agents carry only a fake key; the real key is added here.
A's gateway cannot serve Gemini yet, so this one stays the default until it can.
"""

import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath

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
CONFIG_AGENTS_DIR = Path("/config/agents")
FOLDERS_DIR = Path("/data/folders")

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


def folder_name(host_path: str) -> str:
    windows = "\\" in host_path or (len(host_path) >= 2 and host_path[1] == ":")
    return (PureWindowsPath(host_path) if windows else PurePosixPath(host_path)).name


def agent_folders(agent: str) -> dict[str, dict]:
    """Allowed folders for `agent` from /config/agents/<agent>/permissions.json: {mount_name: folder_dict}."""
    perm_file = CONFIG_AGENTS_DIR / agent / "permissions.json"
    if not perm_file.is_file():
        return {}
    try:
        data = json.loads(perm_file.read_text(encoding="utf-8"))
        folders = data.get("permissions", {}).get("folders", [])
        return {folder_name(f["path"]): f for f in folders if "path" in f}
    except (OSError, ValueError, KeyError):
        return {}


def resolve_mounted_file(agent: str, path: str) -> tuple[Path, dict] | None:
    """Resolve `<folder>/<inside>` under /data/folders/<folder> if allowed for `agent`."""
    cleaned = path.strip().replace("\\", "/").lstrip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if not parts:
        return None
    folder, inside = parts[0], parts[1:]
    allowed = agent_folders(agent).get(folder)
    mount = FOLDERS_DIR / folder
    if allowed is None or not mount.is_dir():
        return None
    base = mount.resolve()
    target = base.joinpath(*inside).resolve()
    if not target.is_relative_to(base):
        raise PermissionError(f"Heimdall refused path outside folder {folder}")
    return target, allowed


@mcp.tool(structured_output=False)
async def files_list(ctx: Context, folder: str = "") -> str:
    """List what you may read. With no folder: your folders, each with its label and
    whether you may write to it. With a folder name (or "<folder>/<subfolder>"): the files
    in it, as paths to pass to files_read."""
    agent = caller(ctx)
    log("tool_call", agent=agent, tool="files_list", path=folder or None, decision="allow")
    allowed = agent_folders(agent)
    if not allowed:
        return "\n".join(FAKE_FILES)
    if not folder.strip():
        return "\n".join(
            f"{name} ({info.get('label', 'private')}, {'writable' if info.get('write') else 'read only'})"
            for name, info in allowed.items()
        )
    resolved = resolve_mounted_file(agent, folder)
    if resolved is None or not resolved[0].is_dir():
        raise PermissionError(f"Heimdall refused files_list: {folder} is not an allowed folder")
    target, _ = resolved
    mount_name = folder.strip().replace("\\", "/").strip("/").split("/")[0]
    base = (FOLDERS_DIR / mount_name).resolve()
    files = [
        f"{mount_name}/{entry.relative_to(base).as_posix()}"
        for entry in sorted(target.rglob("*"))
        if entry.is_file() and entry.resolve().is_relative_to(base)
    ]
    return "\n".join(files[:200]) or "(empty)"


@mcp.tool(structured_output=False)
async def files_read(path: str, ctx: Context) -> str:
    """Read a file from the user's allowed folders."""
    agent = caller(ctx)
    log("tool_call", agent=agent, tool="files_read", path=path, decision="allow")
    if path in FAKE_FILES:
        return FAKE_FILES[path]
    resolved = resolve_mounted_file(agent, path)
    if resolved is not None and resolved[0].is_file():
        return resolved[0].read_text(encoding="utf-8", errors="replace")
    return FAKE_FILES.get(path, f"(fake gateway has no file named {path})")


@mcp.tool(structured_output=False)
async def files_write(path: str, text: str, ctx: Context) -> str:
    """Create or replace a text file. `path` is "<folder>/<file name>"; the folder must be writable."""
    agent = caller(ctx)
    resolved = resolve_mounted_file(agent, path)
    if resolved is None or not resolved[1].get("write"):
        log("tool_call", agent=agent, tool="files_write", path=path, decision="deny")
        raise PermissionError(f"Heimdall refused files_write on {path}: folder is not writable")
    target, _ = resolved
    target.write_text(text, encoding="utf-8")
    log("tool_call", agent=agent, tool="files_write", path=path, decision="allow")
    return f"Wrote {len(text)} characters to {path}."


@mcp.tool(structured_output=False)
async def gmail_read(ctx: Context, query: str = "", limit: int = 10) -> str:
    """Read the user's email, newest first."""
    agent = caller(ctx)
    log("tool_call", agent=agent, tool="gmail_read", path=None, decision="allow")
    return "From: {{EMAIL_1}}\nSubject: Project update\n\nHere is the latest update on the reading list."


@mcp.tool(structured_output=False)
async def gmail_draft(to: str, subject: str, body: str, ctx: Context) -> str:
    """Save an email draft for the user to review later."""
    agent = caller(ctx)
    log("tool_call", agent=agent, tool="gmail_draft", path=None, decision="allow")
    return f"Saved a draft to {to}."


@mcp.tool(structured_output=False)
async def gmail_send(to: str, subject: str, body: str, ctx: Context) -> str:
    """Send an email after user approval."""
    agent = caller(ctx)
    log("tool_call", agent=agent, tool="gmail_send", path=None, decision="allow")
    return f"Sent the email to {to}."


@mcp.tool(structured_output=False)
async def web_fetch(url: str, ctx: Context) -> str:
    """Fetch a public web page (GET only) and return the text a reader would see."""
    agent = caller(ctx)
    log("tool_call", agent=agent, tool="web_fetch", path=url, decision="allow")
    return f"Fetched content from {url}."


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


def fallback_openai_reply(body: dict) -> Response:
    """Offline/fallback OpenAI-style reply when Gemini quota is depleted (402/429) or HEIMDALL_MOCK=1."""
    messages = body.get("messages") or [{}]
    last = messages[-1]
    offered = tools_offered(body)
    read_tool = next((name for name in offered if name and name.endswith("files_read")), None)
    if last.get("role") == "tool":
        msg = {"role": "assistant", "content": f"The tool returned: {last.get('content')}"}
        finish = "stop"
    elif read_tool is not None:
        call = {
            "id": "call_mock_01",
            "type": "function",
            "function": {"name": read_tool, "arguments": json.dumps({"path": "notes.txt"})},
        }
        msg = {"role": "assistant", "content": None, "tool_calls": [call]}
        finish = "tool_calls"
    elif "tool_call" in offered:
        call = {
            "id": "call_mock_01",
            "type": "function",
            "function": {
                "name": "tool_call",
                "arguments": json.dumps(
                    {"calls": [{"name": "mcp__heimdall__files_read", "arguments": {"path": "notes.txt"}}]}
                ),
            },
        }
        msg = {"role": "assistant", "content": None, "tool_calls": [call]}
        finish = "tool_calls"
    else:
        msg = {"role": "assistant", "content": "Hello from Heimdall fallback model."}
        finish = "stop"
    base = {"id": "chatcmpl-mock-01", "created": 0, "model": body.get("model", "mock")}
    if body.get("stream"):
        delta = {"role": "assistant", "content": msg.get("content")}
        if msg.get("tool_calls"):
            delta["tool_calls"] = [{"index": 0, **c} for c in msg["tool_calls"]]
        c1 = {"index": 0, "delta": delta, "finish_reason": None}
        c2 = {"index": 0, "delta": {}, "finish_reason": finish}
        chunks = [
            f"data: {json.dumps({**base, 'object': 'chat.completion.chunk', 'choices': [c1]})}\n\n",
            f"data: {json.dumps({**base, 'object': 'chat.completion.chunk', 'choices': [c2]})}\n\n",
            "data: [DONE]\n\n",
        ]
        return StreamingResponse(iter(chunks), media_type="text/event-stream")
    choice = {"index": 0, "message": msg, "finish_reason": finish}
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    return JSONResponse({**base, "object": "chat.completion", "choices": [choice], "usage": usage})


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
        if reply.status_code in (402, 429) and path.endswith("chat/completions"):
            return fallback_openai_reply(body)
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

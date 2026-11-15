import json
import os
import re

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_URL = "https://generativelanguage.googleapis.com"
FAKE_KEY_PREFIX = "sk-fake-"
HERMES_READ_TOOL = "mcp__heimdall__files_read"
SCRIPTED = os.environ.get("HEIMDALL_SCRIPTED") == "1"
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


@mcp.tool()
def files_read(path: str) -> str:
    """Read a file from the user's allowed folders."""
    log("tool_call", tool="files_read", path=path)
    return FAKE_FILES.get(path, f"(fake gateway has no file named {path})")


@mcp.tool()
def files_list() -> list[str]:
    """List files in the user's allowed folders."""
    log("tool_call", tool="files_list")
    return list(FAKE_FILES)


def scripted_reply(body: dict) -> dict:
    last = body["messages"][-1]["content"]
    blocks = last if isinstance(last, list) else []
    for block in blocks:
        if block.get("type") == "tool_result":
            return {"type": "text", "text": f"The tool returned: {json.dumps(block.get('content'))}"}
    names = [t["name"] for t in body.get("tools", [])]
    read_tool = next((name for name in names if name.endswith("files_read")), None)
    if read_tool:
        return {"type": "tool_use", "id": "toolu_fake_01", "name": read_tool, "input": {"path": "notes.txt"}}
    if "tool_call" in names:
        call = {"name": HERMES_READ_TOOL, "arguments": {"path": "notes.txt"}}
        return {"type": "tool_use", "id": "toolu_fake_01", "name": "tool_call", "input": {"calls": [call]}}
    return {"type": "text", "text": "Fake model: no files_read tool was offered to me."}


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'type': event, **data})}\n\n"


def stream_events(message: dict):
    block = message["content"][0]
    yield sse("message_start", {"message": {**message, "content": [], "stop_reason": None}})
    if block["type"] == "text":
        yield sse("content_block_start", {"index": 0, "content_block": {"type": "text", "text": ""}})
        yield sse("content_block_delta", {"index": 0, "delta": {"type": "text_delta", "text": block["text"]}})
    else:
        yield sse("content_block_start", {"index": 0, "content_block": {**block, "input": {}}})
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        yield sse("content_block_delta", {"index": 0, "delta": delta})
    yield sse("content_block_stop", {"index": 0})
    yield sse(
        "message_delta",
        {"delta": {"stop_reason": message["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": 1}},
    )
    yield sse("message_stop", {})


async def forward_to_provider(request: Request, path: str, body: dict):
    sent_key = request.headers.get("x-api-key") or request.headers.get("authorization", "")
    if FAKE_KEY_PREFIX not in sent_key:
        log("model_blocked", reason="agent did not send its fake key")
        return JSONResponse({"error": "unknown key"}, status_code=401)
    if OPENROUTER_KEY:
        url = f"https://openrouter.ai/api/{path}"
        headers = {"authorization": f"Bearer {OPENROUTER_KEY}"}
        body = {**body, "model": OPENROUTER_MODEL}
    else:
        url = f"https://api.anthropic.com/{path}"
        headers = {"x-api-key": ANTHROPIC_KEY}
        body = {**body, "model": ANTHROPIC_MODEL}
    for name in ("anthropic-version", "anthropic-beta"):
        if name in request.headers:
            headers[name] = request.headers[name]
    log("model_route", model=body.get("model"))
    return await relay_upstream(url, {**headers, "content-type": "application/json"}, {}, json.dumps(body).encode())


async def relay_upstream(url: str, headers: dict, params: dict, content: bytes) -> StreamingResponse:
    client = httpx.AsyncClient(timeout=300)
    request = client.build_request("POST", url, headers=headers, params=params, content=content)
    upstream = await client.send(request, stream=True)
    log("model_forwarded", url=url, status=upstream.status_code)

    async def relay():
        async for chunk in upstream.aiter_bytes():
            yield chunk
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        relay(), status_code=upstream.status_code, media_type=upstream.headers.get("content-type")
    )


@mcp.custom_route("/gemini/{path:path}", methods=["GET", "POST"])
async def gemini(request: Request):
    path = request.path_params["path"]
    if request.method == "GET" or not path.endswith(("GenerateContent", "generateContent", "chat/completions")):
        log("gemini_other", method=request.method, path=path)
        return JSONResponse({"models": []}, status_code=200 if request.method == "GET" else 404)
    sent_key = (
        request.headers.get("x-goog-api-key")
        or request.query_params.get("key")
        or request.headers.get("authorization", "")
    )
    raw = await request.body()
    body = json.loads(raw)
    tools = [f["name"] for t in body.get("tools", []) for f in t.get("functionDeclarations", [])]
    tools += [t["function"]["name"] for t in body.get("tools", []) if "function" in t]
    log("model_call", api_key=sent_key.removeprefix("Bearer "), model=path, tools_offered=tools)
    if FAKE_KEY_PREFIX not in sent_key:
        log("model_blocked", reason="agent did not send its fake key")
        return JSONResponse({"error": "unknown key"}, status_code=401)
    if not GEMINI_KEY:
        return JSONResponse({"error": "GEMINI_API_KEY is not set in the gateway"}, status_code=400)
    if "model" in body:
        raw = json.dumps({**body, "model": GEMINI_MODEL}).encode()
    path = re.sub(r"models/[^/:]+", f"models/{GEMINI_MODEL}", path)
    params = {k: v for k, v in request.query_params.items() if k != "key"}
    headers = {"x-goog-api-key": GEMINI_KEY, "content-type": "application/json"}
    if path.endswith("chat/completions"):
        headers = {"authorization": f"Bearer {GEMINI_KEY}", "content-type": "application/json"}
    return await relay_upstream(f"{GEMINI_URL}/{path}", headers, params, raw)


@mcp.custom_route("/model/{path:path}", methods=["GET", "POST"])
async def model(request: Request):
    path = request.path_params["path"]
    if not path.endswith("messages"):
        log("model_other", method=request.method, path=path)
        return JSONResponse({"data": []})
    body = await request.json()
    log(
        "model_call",
        api_key=request.headers.get("x-api-key") or request.headers.get("authorization"),
        model=body.get("model"),
        tools_offered=[t["name"] for t in body.get("tools", [])],
    )
    if not SCRIPTED and (OPENROUTER_KEY or ANTHROPIC_KEY):
        return await forward_to_provider(request, path, body)
    block = scripted_reply(body)
    message = {
        "id": "msg_fake_01",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "fake"),
        "content": [block],
        "stop_reason": "tool_use" if block["type"] == "tool_use" else "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    if body.get("stream"):
        return StreamingResponse(stream_events(message), media_type="text/event-stream")
    return JSONResponse(message)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")

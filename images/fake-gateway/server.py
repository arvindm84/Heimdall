import json
import os

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
FAKE_KEY = "sk-fake-openclaw-01"
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
    read_tool = next((t["name"] for t in body.get("tools", []) if t["name"].endswith("files_read")), None)
    if read_tool is None:
        return {"type": "text", "text": "Fake model: no files_read tool was offered to me."}
    return {"type": "tool_use", "id": "toolu_fake_01", "name": read_tool, "input": {"path": "notes.txt"}}


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
    if FAKE_KEY not in sent_key:
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
    client = httpx.AsyncClient(timeout=300)
    upstream = await client.send(
        client.build_request("POST", url, headers=headers, json=body),
        stream=True,
    )
    log("model_forwarded", url=url, model=body.get("model"), status=upstream.status_code)

    async def relay():
        async for chunk in upstream.aiter_bytes():
            yield chunk
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        relay(), status_code=upstream.status_code, media_type=upstream.headers.get("content-type")
    )


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
    if OPENROUTER_KEY or ANTHROPIC_KEY:
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

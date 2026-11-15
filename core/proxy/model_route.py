"""The /model/{path} route: the gateway's model proxy.

Agents set their provider base URL to http://gateway:8080/model and send their
fake key. This route checks the key, logs the call, then either answers with
the mock model or relays the request to the real provider with the real key.
Step 3 adds the key tripwire and secret scan; Step 6 adds consent.
"""

import json
from collections.abc import Awaitable, Callable

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from core.firewall import core_client
from core.firewall.config import GatewaySettings

Handler = Callable[[Request], Awaitable[Response]]
# Agent headers we pass on to the provider. Everything else, including the agent's key, is dropped.
FORWARDED_HEADERS = ("anthropic-version", "anthropic-beta")


def sent_key(request: Request) -> str:
    """The key the agent sent: Anthropic style (x-api-key) or OpenAI style (Bearer)."""
    bearer = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    return request.headers.get("x-api-key") or bearer


def make_model_route(settings: GatewaySettings, transport: httpx.AsyncBaseTransport | None = None) -> Handler:
    """Build the route handler for these settings.

    transport: only for tests, to fake the provider.
    """

    async def model_route(request: Request) -> Response:
        path = request.path_params["path"]
        key = sent_key(request)
        # Fail closed: no known fake key, no model access, for any path.
        agent = settings.fake_keys.get(key)
        if agent is None:
            core_client.emit("model_blocked", path=path, reason="missing or unknown fake key")
            return JSONResponse({"error": "Heimdall: unknown key"}, status_code=401)
        # Only the messages call goes upstream. Other calls (such as a model list)
        # get an empty answer, as with the fake gateway.
        if not path.endswith("messages"):
            core_client.emit("model_other", agent=agent, method=request.method, path=path)
            return JSONResponse({"data": []})
        try:
            body = json.loads(await request.body())
        except ValueError:
            body = None
        if not isinstance(body, dict):
            core_client.emit("model_blocked", agent=agent, path=path, reason="body is not a JSON object")
            return JSONResponse({"error": "Heimdall: body must be a JSON object"}, status_code=400)
        # B's runtime test reads api_key and tools_offered from this line. The key
        # here is always a fake one: we only get this far with a known fake key.
        core_client.emit(
            "model_call",
            agent=agent,
            api_key=key,
            model=body.get("model"),
            tools_offered=[tool.get("name") for tool in body.get("tools", [])],
        )
        if settings.provider == "mock":
            return mock_reply(body)
        return await relay(request, path, body, agent, settings, transport)

    return model_route


def upstream_for(settings: GatewaySettings, path: str) -> tuple[str, dict[str, str], str]:
    """Provider URL, auth headers with the real key, and the model the gateway chose."""
    if settings.provider == "openrouter":
        url = f"https://openrouter.ai/api/{path}"
        return url, {"authorization": f"Bearer {settings.openrouter_key}"}, settings.openrouter_model
    return f"https://api.anthropic.com/{path}", {"x-api-key": settings.anthropic_key}, settings.anthropic_model


async def relay(
    request: Request,
    path: str,
    body: dict,
    agent: str,
    settings: GatewaySettings,
    transport: httpx.AsyncBaseTransport | None,
) -> Response:
    """Send the request to the real provider and stream its reply back to the agent."""
    url, headers, model = upstream_for(settings, path)
    headers.update({name: request.headers[name] for name in FORWARDED_HEADERS if name in request.headers})
    # The client must outlive this function (the reply is streamed), so it is
    # closed in chunks() below rather than with `async with`.
    client = httpx.AsyncClient(timeout=300, transport=transport)
    try:
        upstream = await client.send(
            # The agent's "model" field is replaced: the agent cannot pick its own model.
            client.build_request("POST", url, headers=headers, json={**body, "model": model}),
            stream=True,
        )
    except httpx.HTTPError as error:
        await client.aclose()
        core_client.emit("model_upstream_error", agent=agent, url=url, reason=type(error).__name__)
        return JSONResponse({"error": "Heimdall: model provider unreachable"}, status_code=502)
    # Never log `headers`: they hold the real key.
    core_client.emit("model_forwarded", agent=agent, url=url, model=model, status=upstream.status_code)

    async def chunks():
        # Pass bytes through as they arrive so chat replies still stream.
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        chunks(), status_code=upstream.status_code, media_type=upstream.headers.get("content-type")
    )


def scripted_block(body: dict) -> dict:
    """The mock model's one move: call files_read once, then report what it returned."""
    last = body.get("messages", [{}])[-1].get("content")
    # A tool result in the last message means files_read already ran: answer with text.
    for block in last if isinstance(last, list) else []:
        if block.get("type") == "tool_result":
            return {"type": "text", "text": f"The tool returned: {json.dumps(block.get('content'))}"}
    # endswith: the agent may prefix tool names (OpenClaw sends heimdall__files_read).
    names = [tool.get("name", "") for tool in body.get("tools", [])]
    read_tool = next((name for name in names if name.endswith("files_read")), None)
    if read_tool is None:
        return {"type": "text", "text": "Mock model: no files_read tool was offered to me."}
    return {"type": "tool_use", "id": "toolu_mock_01", "name": read_tool, "input": {"path": "notes.txt"}}


def mock_reply(body: dict) -> Response:
    """Wrap the scripted block in an Anthropic Messages reply, streamed if the agent asked for it."""
    block = scripted_block(body)
    message = {
        "id": "msg_mock_01",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "mock"),
        "content": [block],
        "stop_reason": "tool_use" if block["type"] == "tool_use" else "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    if body.get("stream"):
        return StreamingResponse(iter(sse_events(message)), media_type="text/event-stream")
    return JSONResponse(message)


def sse(event: str, data: dict) -> str:
    """One server-sent event in the Anthropic streaming format."""
    return f"event: {event}\ndata: {json.dumps({'type': event, **data})}\n\n"


def sse_events(message: dict) -> list[str]:
    """The event sequence the Anthropic API streams for a one-block message."""
    block = message["content"][0]
    if block["type"] == "text":
        start = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": block["text"]}
    else:
        # Tool calls stream their input as JSON text.
        start = {**block, "input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
    return [
        sse("message_start", {"message": {**message, "content": [], "stop_reason": None}}),
        sse("content_block_start", {"index": 0, "content_block": start}),
        sse("content_block_delta", {"index": 0, "delta": delta}),
        sse("content_block_stop", {"index": 0}),
        sse(
            "message_delta",
            {"delta": {"stop_reason": message["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": 1}},
        ),
        sse("message_stop", {}),
    ]

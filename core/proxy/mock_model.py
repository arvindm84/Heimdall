"""A scripted model for tests and offline demos, in both API styles the agents speak.

Its one move: call files_read once, then report what the tool returned. That is
enough to drive an agent through a full tool round trip with no network.
"""

import json

from starlette.responses import JSONResponse, Response, StreamingResponse

MOCK_PATH = "notes.txt"


def reply(path: str, body: dict) -> Response:
    """Answer in the style of the API the agent called: OpenAI chat/completions or Anthropic messages."""
    if path.endswith("chat/completions"):
        return openai_reply(body)
    return anthropic_reply(body)


def find_read_tool(names: list[str]) -> str | None:
    # endswith: agents may prefix tool names (OpenClaw sends heimdall__files_read).
    return next((name for name in names if name.endswith("files_read")), None)


# ---------- Anthropic messages ----------


def anthropic_block(body: dict) -> dict:
    last = (body.get("messages") or [{}])[-1].get("content")
    # A tool result in the last message means files_read already ran: answer with text.
    for block in last if isinstance(last, list) else []:
        if block.get("type") == "tool_result":
            return {"type": "text", "text": f"The tool returned: {json.dumps(block.get('content'))}"}
    read_tool = find_read_tool([tool.get("name", "") for tool in body.get("tools") or []])
    if read_tool is None:
        return {"type": "text", "text": "Mock model: no files_read tool was offered to me."}
    return {"type": "tool_use", "id": "toolu_mock_01", "name": read_tool, "input": {"path": MOCK_PATH}}


def anthropic_reply(body: dict) -> Response:
    block = anthropic_block(body)
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
        return StreamingResponse(iter(anthropic_events(message)), media_type="text/event-stream")
    return JSONResponse(message)


def anthropic_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps({'type': event, **data})}\n\n"


def anthropic_events(message: dict) -> list[str]:
    """The event sequence the Anthropic API streams for a one-block message."""
    block = message["content"][0]
    if block["type"] == "text":
        start = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": block["text"]}
    else:
        # Tool calls stream their input as JSON text.
        start = {**block, "input": {}}
        delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
    stop = {"delta": {"stop_reason": message["stop_reason"], "stop_sequence": None}, "usage": {"output_tokens": 1}}
    return [
        anthropic_sse("message_start", {"message": {**message, "content": [], "stop_reason": None}}),
        anthropic_sse("content_block_start", {"index": 0, "content_block": start}),
        anthropic_sse("content_block_delta", {"index": 0, "delta": delta}),
        anthropic_sse("content_block_stop", {"index": 0}),
        anthropic_sse("message_delta", stop),
        anthropic_sse("message_stop", {}),
    ]


# ---------- OpenAI chat/completions ----------


def openai_message(body: dict) -> dict:
    last = (body.get("messages") or [{}])[-1]
    # A "tool" message last means files_read already ran: answer with text.
    if last.get("role") == "tool":
        return {"role": "assistant", "content": f"The tool returned: {json.dumps(last.get('content'))}"}
    names = [tool.get("function", {}).get("name", "") for tool in body.get("tools") or []]
    read_tool = find_read_tool(names)
    if read_tool is None:
        return {"role": "assistant", "content": "Mock model: no files_read tool was offered to me."}
    call = {
        "id": "call_mock_01",
        "type": "function",
        "function": {"name": read_tool, "arguments": json.dumps({"path": MOCK_PATH})},
    }
    return {"role": "assistant", "content": None, "tool_calls": [call]}


def openai_reply(body: dict) -> Response:
    message = openai_message(body)
    finish = "tool_calls" if message.get("tool_calls") else "stop"
    base = {"id": "chatcmpl-mock-01", "created": 0, "model": body.get("model", "mock")}
    if body.get("stream"):
        return StreamingResponse(iter(openai_chunks(base, message, finish)), media_type="text/event-stream")
    choice = {"index": 0, "message": message, "finish_reason": finish}
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    return JSONResponse({**base, "object": "chat.completion", "choices": [choice], "usage": usage})


def openai_chunks(base: dict, message: dict, finish: str) -> list[str]:
    """Streamed form: one chunk with the whole delta, one with the finish reason, then [DONE]."""
    delta = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        # Streamed tool calls carry an index so clients can join partial chunks.
        delta["tool_calls"] = [{"index": 0, **call} for call in message["tool_calls"]]

    def chunk(delta: dict, finish_reason: str | None) -> str:
        choice = {"index": 0, "delta": delta, "finish_reason": finish_reason}
        return f"data: {json.dumps({**base, 'object': 'chat.completion.chunk', 'choices': [choice]})}\n\n"

    return [chunk(delta, None), chunk({}, finish), "data: [DONE]\n\n"]

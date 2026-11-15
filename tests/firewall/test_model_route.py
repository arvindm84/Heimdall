"""The /model route: fake-key check, routing by API style, real-key swap, mock model.

Requests go through Starlette's TestClient. Providers are faked with
httpx.MockTransport, so no test touches the network. All keys are made up.
"""

import json

import httpx
import pytest
from starlette.testclient import TestClient

from core.firewall.config import GatewaySettings
from core.gateway import build_gateway
from tests.firewall.helpers import FAKE_KEY

GEMINI_KEY = "AIza-test-not-a-real-key"
ANTHROPIC_KEY = "sk-ant-test-not-a-real-key"
LIVE = GatewaySettings(fake_keys={FAKE_KEY: "openclaw"}, gemini_key=GEMINI_KEY, anthropic_key=ANTHROPIC_KEY)

# Shaped like the agents' requests: OpenClaw prefixes tool names with heimdall__.
ANTHROPIC_REQUEST = {
    "model": "claude-haiku-4-5",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Read my notes file"}],
    "tools": [{"name": "heimdall__files_read", "input_schema": {"type": "object"}}],
}
OPENAI_REQUEST = {
    "model": "gemini-flash-lite-latest",
    "messages": [{"role": "user", "content": "Read my notes file"}],
    "tools": [{"type": "function", "function": {"name": "heimdall__files_read", "parameters": {"type": "object"}}}],
}
AS_OPENCLAW = {"authorization": f"Bearer {FAKE_KEY}"}


def client_for(settings, transport=None):
    """HTTP client for the whole gateway app; transport fakes the model provider."""
    return TestClient(build_gateway(settings, transport=transport).streamable_http_app())


def recording_provider(seen: list[httpx.Request], status: int = 200, body: dict | None = None):
    """A fake provider that records each request it gets."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body or {"ok": True})

    return httpx.MockTransport(handler)


# ---------- key check ----------


def test_missing_key_is_blocked(mock_settings, events):
    response = client_for(mock_settings).post("/model/v1/messages", json=ANTHROPIC_REQUEST)
    assert response.status_code == 401
    assert [event["kind"] for event in events] == ["model_blocked"]


def test_unknown_key_is_blocked(mock_settings, events):
    headers = {"x-api-key": "sk-fake-someone-else-01"}
    response = client_for(mock_settings).post("/model/v1/messages", json=ANTHROPIC_REQUEST, headers=headers)
    assert response.status_code == 401


def test_model_list_without_key_is_401(mock_settings, events):
    # B's check_sealed_and_routed expects exactly this.
    assert client_for(mock_settings).get("/model/models").status_code == 401


def test_other_paths_get_a_stub(mock_settings, events):
    # Clients may list models; that never reaches a provider.
    response = client_for(mock_settings).get("/model/models", headers=AS_OPENCLAW)
    assert response.json() == {"data": []}


def test_bad_json_is_rejected(mock_settings, events):
    headers = {**AS_OPENCLAW, "content-type": "application/json"}
    response = client_for(mock_settings).post("/model/chat/completions", content=b"{not json", headers=headers)
    assert response.status_code == 400


# ---------- model_call event (B's tests read it) ----------


@pytest.mark.parametrize(
    "path, request_body", [("v1/messages", ANTHROPIC_REQUEST), ("chat/completions", OPENAI_REQUEST)]
)
def test_model_call_event_has_fake_key_and_tools(mock_settings, events, path, request_body):
    client_for(mock_settings).post(f"/model/{path}", json=request_body, headers=AS_OPENCLAW)
    call = next(event for event in events if event["kind"] == "model_call")
    assert call["agent"] == "openclaw"
    assert call["api_key"] == FAKE_KEY
    assert call["tools_offered"] == ["heimdall__files_read"]


# ---------- live providers ----------


def test_chat_completions_goes_to_gemini_with_real_key(events):
    seen: list[httpx.Request] = []
    response = client_for(LIVE, recording_provider(seen)).post(
        "/model/chat/completions", json=OPENAI_REQUEST, headers=AS_OPENCLAW
    )
    assert response.status_code == 200
    sent = seen[0]
    assert str(sent.url).startswith("https://generativelanguage.googleapis.com/")
    assert sent.headers["authorization"] == f"Bearer {GEMINI_KEY}"
    # The model the agent's config names (set by B's manager) passes through.
    assert json.loads(sent.content)["model"] == "gemini-flash-lite-latest"
    assert FAKE_KEY not in sent.content.decode()
    forwarded = next(event for event in events if event["kind"] == "model_forwarded")
    assert forwarded["url"].startswith("https://generativelanguage.googleapis.com/")


def test_messages_goes_to_anthropic_with_real_key(events):
    seen: list[httpx.Request] = []
    headers = {"x-api-key": FAKE_KEY, "anthropic-version": "2023-06-01"}
    client_for(LIVE, recording_provider(seen)).post("/model/v1/messages", json=ANTHROPIC_REQUEST, headers=headers)
    sent = seen[0]
    assert str(sent.url) == "https://api.anthropic.com/v1/messages"
    assert sent.headers["x-api-key"] == ANTHROPIC_KEY
    assert sent.headers["anthropic-version"] == "2023-06-01"


def test_real_keys_never_reach_the_event_lines(events):
    client_for(LIVE, recording_provider([])).post("/model/chat/completions", json=OPENAI_REQUEST, headers=AS_OPENCLAW)
    client_for(LIVE, recording_provider([])).post("/model/v1/messages", json=ANTHROPIC_REQUEST, headers=AS_OPENCLAW)
    logged = json.dumps(events)
    assert GEMINI_KEY not in logged and ANTHROPIC_KEY not in logged


def test_replayed_tool_calls_get_a_thought_signature(events):
    seen: list[httpx.Request] = []
    call = {"id": "c1", "type": "function", "function": {"name": "heimdall__files_read", "arguments": "{}"}}
    body = {**OPENAI_REQUEST, "messages": [*OPENAI_REQUEST["messages"], {"role": "assistant", "tool_calls": [call]}]}
    client_for(LIVE, recording_provider(seen)).post("/model/chat/completions", json=body, headers=AS_OPENCLAW)
    replayed = json.loads(seen[0].content)["messages"][1]["tool_calls"][0]
    assert replayed["extra_content"]["google"]["thought_signature"] == "skip_thought_signature_validator"


def test_missing_real_key_gives_502_and_sends_nothing(events):
    seen: list[httpx.Request] = []
    settings = GatewaySettings(fake_keys={FAKE_KEY: "openclaw"}, anthropic_key=ANTHROPIC_KEY)
    response = client_for(settings, recording_provider(seen)).post(
        "/model/chat/completions", json=OPENAI_REQUEST, headers=AS_OPENCLAW
    )
    assert response.status_code == 502
    assert seen == []
    assert events[-1]["kind"] == "model_blocked"


def test_provider_error_is_passed_on_and_logged(events):
    provider = recording_provider([], status=400, body={"error": "bad request"})
    response = client_for(LIVE, provider).post("/model/chat/completions", json=OPENAI_REQUEST, headers=AS_OPENCLAW)
    assert response.status_code == 400
    assert events[-1]["kind"] == "model_error"
    assert "bad request" in events[-1]["body"]


def test_provider_down_gives_502(events):
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    response = client_for(LIVE, httpx.MockTransport(down)).post(
        "/model/chat/completions", json=OPENAI_REQUEST, headers=AS_OPENCLAW
    )
    assert response.status_code == 502
    assert events[-1]["kind"] == "model_upstream_error"


# ---------- mock model ----------


def test_mock_anthropic_asks_for_files_read(mock_settings, events):
    response = client_for(mock_settings).post("/model/v1/messages", json=ANTHROPIC_REQUEST, headers=AS_OPENCLAW)
    block = response.json()["content"][0]
    assert block["type"] == "tool_use" and block["name"] == "heimdall__files_read"


def test_mock_anthropic_streams(mock_settings, events):
    body = {**ANTHROPIC_REQUEST, "stream": True}
    response = client_for(mock_settings).post("/model/v1/messages", json=body, headers=AS_OPENCLAW)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: message_stop" in response.text


def test_mock_openai_asks_for_files_read(mock_settings, events):
    response = client_for(mock_settings).post("/model/chat/completions", json=OPENAI_REQUEST, headers=AS_OPENCLAW)
    choice = response.json()["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "heimdall__files_read"


def test_mock_openai_reports_the_tool_result(mock_settings, events):
    messages = [*OPENAI_REQUEST["messages"], {"role": "tool", "tool_call_id": "call_mock_01", "content": "hello"}]
    response = client_for(mock_settings).post(
        "/model/chat/completions", json={**OPENAI_REQUEST, "messages": messages}, headers=AS_OPENCLAW
    )
    assert "hello" in response.json()["choices"][0]["message"]["content"]


def test_mock_openai_streams(mock_settings, events):
    body = {**OPENAI_REQUEST, "stream": True}
    response = client_for(mock_settings).post("/model/chat/completions", json=body, headers=AS_OPENCLAW)
    lines = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    first = json.loads(lines[0].removeprefix("data: "))
    assert first["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "heimdall__files_read"

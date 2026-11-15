"""Step 0: the /model route checks the fake key, logs the call, and answers or relays.

Requests go through Starlette's TestClient. The real provider is faked with
httpx.MockTransport, so no test touches the network. All keys are made up.
"""

import json

import httpx
from starlette.testclient import TestClient

from core.firewall.config import GatewaySettings
from core.gateway import build_gateway

FAKE_KEY = "sk-fake-openclaw-01"
REAL_KEY = "sk-ant-test-not-a-real-key"
# Shaped like OpenClaw's request: its tool names carry the heimdall__ prefix.
REQUEST = {
    "model": "default",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Read my notes file"}],
    "tools": [{"name": "heimdall__files_read", "input_schema": {"type": "object"}}],
}


def client_for(settings, transport=None):
    """HTTP client for the whole gateway app; transport fakes the model provider."""
    return TestClient(build_gateway(settings, transport=transport).streamable_http_app())


def test_mock_provider_asks_for_files_read(mock_settings, events):
    response = client_for(mock_settings).post("/model/v1/messages", json=REQUEST, headers={"x-api-key": FAKE_KEY})
    assert response.status_code == 200
    block = response.json()["content"][0]
    assert block["type"] == "tool_use"
    assert block["name"] == "heimdall__files_read"


def test_mock_provider_streams(mock_settings, events):
    body = {**REQUEST, "stream": True}
    response = client_for(mock_settings).post("/model/v1/messages", json=body, headers={"x-api-key": FAKE_KEY})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: message_stop" in response.text


def test_model_call_event_has_fake_key_and_tools(mock_settings, events):
    # tests/runtime/test_manager.py reads these two fields from the gateway logs.
    client_for(mock_settings).post("/model/v1/messages", json=REQUEST, headers={"x-api-key": FAKE_KEY})
    call = next(event for event in events if event["kind"] == "model_call")
    assert call["agent"] == "openclaw"
    assert call["api_key"] == FAKE_KEY
    assert call["tools_offered"] == ["heimdall__files_read"]


def test_bearer_header_also_identifies_the_agent(mock_settings, events):
    headers = {"authorization": f"Bearer {FAKE_KEY}"}
    response = client_for(mock_settings).post("/model/v1/messages", json=REQUEST, headers=headers)
    assert response.status_code == 200


def test_missing_key_is_blocked(mock_settings, events):
    response = client_for(mock_settings).post("/model/v1/messages", json=REQUEST)
    assert response.status_code == 401
    assert [event["kind"] for event in events] == ["model_blocked"]


def test_unknown_key_is_blocked(mock_settings, events):
    headers = {"x-api-key": "sk-fake-someone-else-01"}
    response = client_for(mock_settings).post("/model/v1/messages", json=REQUEST, headers=headers)
    assert response.status_code == 401
    assert events[0]["kind"] == "model_blocked"


def test_other_paths_get_a_stub(mock_settings, events):
    # Clients may list models; that never reaches the provider.
    response = client_for(mock_settings).get("/model/v1/models", headers={"x-api-key": FAKE_KEY})
    assert response.json() == {"data": []}


def test_bad_json_is_rejected(mock_settings, events):
    headers = {"x-api-key": FAKE_KEY, "content-type": "application/json"}
    response = client_for(mock_settings).post("/model/v1/messages", content=b"{not json", headers=headers)
    assert response.status_code == 400


def test_anthropic_upstream_gets_real_key_and_chosen_model(events):
    seen: list[httpx.Request] = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"type": "message", "content": []})

    settings = GatewaySettings(
        fake_keys={FAKE_KEY: "openclaw"},
        provider="anthropic",
        anthropic_key=REAL_KEY,
        anthropic_model="claude-sonnet-5-5",
    )
    headers = {"x-api-key": FAKE_KEY, "anthropic-version": "2023-06-01"}
    response = client_for(settings, httpx.MockTransport(upstream)).post(
        "/model/v1/messages", json=REQUEST, headers=headers
    )

    assert response.status_code == 200
    # The provider sees the real key and the gateway's model; the fake key and
    # the real key never leak into the request body or the event lines.
    sent = seen[0]
    assert str(sent.url) == "https://api.anthropic.com/v1/messages"
    assert sent.headers["x-api-key"] == REAL_KEY
    assert sent.headers["anthropic-version"] == "2023-06-01"
    assert json.loads(sent.content)["model"] == "claude-sonnet-5-5"
    assert FAKE_KEY not in sent.content.decode()
    assert all(REAL_KEY not in json.dumps(event) for event in events)


def test_upstream_down_gives_502(events):
    def upstream(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    settings = GatewaySettings(fake_keys={FAKE_KEY: "openclaw"}, provider="anthropic", anthropic_key=REAL_KEY)
    response = client_for(settings, httpx.MockTransport(upstream)).post(
        "/model/v1/messages", json=REQUEST, headers={"x-api-key": FAKE_KEY}
    )
    assert response.status_code == 502
    assert events[-1]["kind"] == "model_upstream_error"

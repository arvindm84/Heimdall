"""Route tests for launch/stop/kill/agents. The agent manager is faked, so no Docker is needed."""

import json
import subprocess

import pytest

from agents import manager
from core.contracts.agents import OpenedAgent
from backend.app import app
from backend.services import agent_service


@pytest.fixture
def calls(monkeypatch):
    """Replace the manager's Docker functions and record how they were called."""
    recorded = []

    def open_agent(agent, permissions, provider="gemini", model=None):
        manager.profile(agent)  # same unknown-agent check as the real one
        recorded.append(("open", agent, permissions, provider, model))
        return OpenedAgent(agent=agent, chat_url="http://127.0.0.1:7681/", chat_user="heimdall", chat_token="t")

    monkeypatch.setattr(manager, "open_agent", open_agent)
    monkeypatch.setattr(manager, "stop_agent", lambda agent: recorded.append(("stop", agent)))
    monkeypatch.setattr(manager, "kill_agent", lambda agent: recorded.append(("kill", agent)))
    agent_service._opened.clear()
    return recorded


@pytest.fixture
def client():
    return app.test_client()


def test_launch_passes_the_users_choices_to_the_manager(client, calls, tmp_path):
    config = {
        "folders": [{"path": str(tmp_path), "label": "confidential"}],
        "tools": ["files_read"],
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
    }
    response = client.post("/api/launch", json={"agent": "openclaw", "config": config})

    assert response.status_code == 201
    assert response.json == {
        "agent": "openclaw",
        "chat_url": "http://127.0.0.1:7681/",
        "chat_user": "heimdall",
        "chat_token": "t",
    }
    _, agent, permissions, provider, model = calls[0]
    assert (agent, provider, model) == ("openclaw", "anthropic", "claude-haiku-4-5")
    assert permissions.tools == ["files_read"]
    assert permissions.folders[0].label == "confidential"
    assert permissions.folders[0].write is False


def test_launch_with_empty_config_uses_defaults(client, calls):
    response = client.post("/api/launch", json={"agent": "hermes", "config": {}})
    assert response.status_code == 201
    assert calls[0][3:] == ("gemini", None)


@pytest.mark.parametrize(
    "body",
    [
        {"agent": "openclaw"},  # no config
        {"agent": "openclaw", "config": "nope"},
        {"agent": "not-an-agent", "config": {}},
        {"agent": "openclaw", "config": {"folders": [{"path": "/definitely/not/here"}]}},
        {"agent": "openclaw", "config": {"folders": [{"path": "relative/path"}]}},
        {"agent": "openclaw", "config": {"folders": [{"path": "/tmp", "label": "secret"}]}},
    ],
)
def test_bad_launch_requests_get_a_400(client, calls, body):
    response = client.post("/api/launch", json=body)
    assert response.status_code == 400
    assert "error" in response.json
    assert not [call for call in calls if call[0] == "open" and call[1] != "not-an-agent"]


def test_agents_lists_open_chats_until_they_are_killed(client, calls):
    client.post("/api/launch", json={"agent": "openclaw", "config": {}})
    listed = {entry["name"]: entry["chat"] for entry in client.get("/api/agents").json["agents"]}
    assert listed["openclaw"]["chat_token"] == "t"
    assert listed["hermes"] is None

    assert client.post("/api/kill", json={"agent": "openclaw"}).status_code == 200
    assert ("kill", "openclaw") in calls
    listed = {entry["name"]: entry["chat"] for entry in client.get("/api/agents").json["agents"]}
    assert listed["openclaw"] is None


def test_agents_lists_every_provider_with_its_default_model(client):
    providers = client.get("/api/agents").json["providers"]
    assert providers == [{"name": name, "default_model": model} for name, model in manager.PROVIDERS.items()]


def test_launch_passes_skills_through(client, calls):
    response = client.post("/api/launch", json={"agent": "openclaw", "config": {"skills": ["weather-helper"]}})
    assert response.status_code == 201
    assert calls[0][2].skills == ["weather-helper"]


def test_stop_and_kill_need_an_agent(client, calls):
    assert client.post("/api/stop", json={"agent": "hermes"}).status_code == 200
    assert ("stop", "hermes") in calls
    assert client.post("/api/kill", json={}).status_code == 400
    assert client.post("/api/stop", json={}).status_code == 400


@pytest.mark.parametrize(
    "stderr, status",
    [
        ("Error: port 7681 is already allocated", 500),
        ("Cannot connect to the Docker daemon", 503),  # Docker Desktop not running
    ],
)
def test_docker_failure_comes_back_as_json_with_the_reason(client, calls, monkeypatch, stderr, status):
    def fail(agent):
        raise subprocess.CalledProcessError(1, ["docker", "compose"], stderr=stderr)

    monkeypatch.setattr(manager, "kill_agent", fail)
    response = client.post("/api/kill", json={"agent": "openclaw"})
    assert response.status_code == status
    assert response.json["detail"] == stderr


# Firewall events: POST /api/event -> `event: firewall` on /api/events

from backend.services import event_service


@pytest.fixture
def events():
    event_service.clear()
    yield event_service
    event_service.clear()


TOOL_CALL = {"kind": "tool_call", "agent": "openclaw", "tool": "files_read", "path": "docs/plan.md", "decision": "allow"}


def test_event_is_kept_with_an_id_and_time(client, events):
    response = client.post("/api/event", json=TOOL_CALL)
    assert response.status_code == 204

    [stored] = events.since(0)
    assert stored.items() >= TOOL_CALL.items()
    assert stored["id"] == 1 and stored["time"]


def test_gateway_cannot_overwrite_the_id(client, events):
    client.post("/api/event", json={**TOOL_CALL, "id": 99})
    assert events.since(0)[0]["id"] == 1


@pytest.mark.parametrize("body", [{"agent": "openclaw"}, ["kind"], "tool_call"])
def test_event_without_a_kind_gets_a_400(client, events, body):
    response = client.post("/api/event", json=body)
    assert response.status_code == 400
    assert events.since(0) == []


def test_oldest_events_are_dropped(events):
    for n in range(events.MAX_EVENTS + 1):
        events.add({"kind": "tool_call", "n": n})
    kept = events.since(0)
    assert len(kept) == events.MAX_EVENTS
    assert kept[0]["n"] == 1  # event 0 was pushed out


def test_events_stream_sends_firewall_events(client, events):
    client.post("/api/event", json=TOOL_CALL)
    client.post("/api/event", json={"kind": "model_blocked", "agent": "hermes", "rule_id": "key_theft_attempt"})

    # Read the stream until both events have arrived (it never ends on its own).
    stream = client.get("/api/events", buffered=False).response
    text = ""
    for chunk in stream:
        text += chunk.decode() if isinstance(chunk, bytes) else chunk
        if text.count("event: firewall") == 2:
            break
    stream.close()

    messages = [m for m in text.split("\n\n") if m.startswith("event: firewall")]
    sent = [json.loads(m.split("data: ", 1)[1]) for m in messages]
    assert [e["kind"] for e in sent] == ["tool_call", "model_blocked"]
    assert [e["id"] for e in sent] == [1, 2]


# Answers: /api/raise waits, /api/response wakes it. Optional scope on consent approvals.

import threading
import time

from backend.services import notification_service


def raise_in_background(client, body):
    """POST /api/raise in a thread (it waits for the answer). Returns (thread, result dict, request_id)."""
    result = {}
    thread = threading.Thread(target=lambda: result.update(response=client.post("/api/raise", json=body).json))
    thread.start()
    for _ in range(100):
        if pending := notification_service.list_pending():
            return thread, result, pending[0]["request_id"]
        time.sleep(0.01)
    raise AssertionError("the question never became pending")


CONSENT = {"kind": "consent", "container_id": "hermes", "question": "Send taxes/return.txt to Gemini?", "file": "taxes/return.txt"}
APPROVAL = {"kind": "approval", "container_id": "hermes", "question": "Send this email?", "tool": "gmail_send"}


def test_plain_approve_comes_back_without_a_scope(client):
    thread, result, request_id = raise_in_background(app.test_client(), APPROVAL)
    assert client.post("/api/response", json={"request_id": request_id, "decision": "approve"}).status_code == 200
    thread.join()
    assert result["response"] == {"decision": "approve"}


@pytest.mark.parametrize("scope", ["once", "folder"])
def test_consent_approve_passes_the_scope_on(client, scope):
    thread, result, request_id = raise_in_background(app.test_client(), CONSENT)
    answer = {"request_id": request_id, "decision": "approve", "scope": scope}
    assert client.post("/api/response", json=answer).status_code == 200
    thread.join()
    assert result["response"] == {"decision": "approve", "scope": scope}


@pytest.mark.parametrize(
    "question, answer",
    [
        (APPROVAL, {"decision": "approve", "scope": "folder"}),  # not a consent question
        (CONSENT, {"decision": "deny", "scope": "folder"}),  # scope only with approve
        (CONSENT, {"decision": "approve", "scope": "forever"}),  # unknown scope
    ],
)
def test_misplaced_scope_gets_a_400_and_the_question_stays_open(client, question, answer):
    thread, result, request_id = raise_in_background(app.test_client(), question)
    response = client.post("/api/response", json={"request_id": request_id, **answer})
    assert response.status_code == 400
    # Still waiting: a bad answer must not count as one. Answer properly to finish.
    assert notification_service.list_pending()
    client.post("/api/response", json={"request_id": request_id, "decision": "deny"})
    thread.join()
    assert result["response"] == {"decision": "deny"}


def test_no_answer_is_a_deny(client, monkeypatch):
    monkeypatch.setattr(notification_service, "TIMEOUT_SECONDS", 0.05)
    assert client.post("/api/raise", json=APPROVAL).json == {"decision": "deny"}


# Session token and Origin check (on in the desktop app, off by default).

from backend import app as app_module


@pytest.fixture
def locked(monkeypatch, tmp_path):
    """The desktop app's settings, with a stand-in built UI so / can answer."""
    (tmp_path / "index.html").write_text("<html></html>")
    monkeypatch.setattr(app_module, "FRONTEND_DIST", tmp_path)
    monkeypatch.setitem(app.config, "REQUIRE_TOKEN", True)
    return app.test_client()


def test_api_needs_the_session_cookie(locked):
    assert locked.get("/api/agents").status_code == 401
    locked.get("/")  # the window loads the page and gets the cookie
    assert locked.get("/api/agents").status_code == 200


def test_page_on_another_site_is_refused(locked):
    locked.get("/")
    response = locked.post("/api/response", json={"request_id": "x", "decision": "deny"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    response = locked.post("/api/response", json={"request_id": "x", "decision": "deny"}, headers={"Origin": app_module.OWN_ORIGIN})
    assert response.status_code == 404  # got through the check; no such request


def test_cookie_is_http_only_and_strict(locked):
    cookie = locked.get("/").headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_gateway_routes_need_no_cookie(locked, events):
    assert locked.post("/api/event", json={"kind": "tool_call"}).status_code == 204
    assert locked.post("/api/raise", json={"container_id": "openclaw"}).status_code == 400  # reached the route


# Real API keys: saved in the system key store (an in-memory stand-in here), passed to the gateway only.

import os

import keyring
import keyring.backend

from backend.services import key_service


class MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if self.store.pop((service, username), None) is None:
            raise keyring.errors.PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    """Every test here: never touch the real Keychain, and leave the environment as it was."""
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    for variable in key_service.KEY_ENV.values():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(key_service, "_set_here", set())
    yield
    keyring.set_keyring(previous)


def test_saved_key_is_reported_but_never_returned(client):
    assert client.get("/api/keys").json == {"gemini": False, "anthropic": False}
    assert client.post("/api/keys", json={"provider": "gemini", "key": "real-key-123"}).status_code == 204
    response = client.get("/api/keys")
    assert response.json == {"gemini": True, "anthropic": False}
    assert "real-key-123" not in response.get_data(as_text=True)


def test_launch_hands_saved_keys_to_compose(client, calls):
    client.post("/api/keys", json={"provider": "anthropic", "key": "real-key-456"})
    client.post("/api/launch", json={"agent": "openclaw", "config": {}})
    assert os.environ["ANTHROPIC_API_KEY"] == "real-key-456"


def test_removed_key_stops_being_passed_on(client, calls):
    client.post("/api/keys", json={"provider": "gemini", "key": "real-key-789"})
    client.post("/api/launch", json={"agent": "openclaw", "config": {}})
    client.post("/api/keys", json={"provider": "gemini", "key": ""})  # empty removes it
    client.post("/api/launch", json={"agent": "openclaw", "config": {}})
    assert "GEMINI_API_KEY" not in os.environ
    assert client.get("/api/keys").json["gemini"] is False


@pytest.mark.parametrize("body", [{"provider": "openai", "key": "k"}, {"provider": "gemini"}, {"provider": "gemini", "key": 5}])
def test_bad_key_requests_get_a_400(client, body):
    assert client.post("/api/keys", json=body).status_code == 400

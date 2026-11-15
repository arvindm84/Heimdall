"""Step 0: ask() passes the user's answer through, and anything wrong means deny.

The back end's /raise is faked with httpx.MockTransport.
"""

import json

import httpx
import pytest

from core.firewall import core_client

pytestmark = pytest.mark.anyio


async def ask_with(handler) -> str:
    """Ask one fixed approval question against a fake back end."""
    return await core_client.ask(
        "approval", "openclaw", "Send this email?", {"tool": "gmail_send"}, transport=httpx.MockTransport(handler)
    )


async def test_approve_is_passed_through(events):
    sent: list[dict] = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"decision": "approve"})

    assert await ask_with(handler) == "approve"
    assert sent[0]["container_id"] == "openclaw"
    assert sent[0]["question"] == "Send this email?"
    assert sent[0]["kind"] == "approval"
    assert sent[0]["tool"] == "gmail_send"


async def test_details_cannot_override_who_is_asking(events):
    sent: list[dict] = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"decision": "deny"})

    await core_client.ask(
        "approval", "openclaw", "q", {"container_id": "other"}, transport=httpx.MockTransport(handler)
    )
    assert sent[0]["container_id"] == "openclaw"


def raise_connect_error(request):
    raise httpx.ConnectError("refused")


def raise_timeout(request):
    raise httpx.ReadTimeout("slow")


@pytest.mark.parametrize(
    "handler",
    [
        raise_connect_error,  # back end not running
        raise_timeout,  # user never answered
        lambda request: httpx.Response(200, content=b"not json"),
        lambda request: httpx.Response(200, json=["approve"]),  # JSON, wrong shape
        lambda request: httpx.Response(200, json={"decision": "yes please"}),  # unknown answer
        lambda request: httpx.Response(500, json={"decision": "approve"}),  # error status wins
    ],
)
async def test_anything_wrong_means_deny(handler, events):
    assert await ask_with(handler) == "deny"
    assert events[-1]["kind"] == "ask_failed"


# ---------- events to the dashboard ----------


def forwarding(monkeypatch, handler):
    """Point emit at a fake dashboard. Returns nothing; events land wherever `handler` puts them."""
    monkeypatch.setattr(core_client, "EVENTS_URL", "http://core.test/event")
    monkeypatch.setattr(core_client, "events_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(core_client, "_queue", None)  # a fresh sender thread with this transport


def test_events_are_posted_to_the_dashboard_in_order(monkeypatch, capsys):
    posted = []
    forwarding(monkeypatch, lambda request: posted.append(json.loads(request.content)) or httpx.Response(200))
    core_client.emit("tool_call", agent="openclaw", n=1)
    core_client.emit("tool_call", agent="openclaw", n=2)
    core_client._queue.join()
    assert posted == [{"kind": "tool_call", "agent": "openclaw", "n": 1}, {"kind": "tool_call", "agent": "openclaw", "n": 2}]
    assert capsys.readouterr().out.count('"kind": "tool_call"') == 2  # stdout keeps the record too


def test_a_dead_dashboard_does_not_break_emit(monkeypatch):
    def down(request):
        raise httpx.ConnectError("down")

    forwarding(monkeypatch, down)
    core_client.emit("tool_call", agent="openclaw")
    core_client._queue.join()  # dropped quietly; the next event still goes
    core_client.emit("tool_call", agent="openclaw")
    core_client._queue.join()


def test_without_an_events_url_nothing_is_posted(monkeypatch):
    monkeypatch.setattr(core_client, "EVENTS_URL", "")
    monkeypatch.setattr(core_client, "_queue", None)
    core_client.emit("tool_call", agent="openclaw")
    assert core_client._queue is None

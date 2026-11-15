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

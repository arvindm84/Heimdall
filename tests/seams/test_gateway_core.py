"""Seam 2 (A and C): the gateway asks the user through C's real back end.

C's Flask app (backend/app.py) runs in a thread on a free local port. The gateway's
gmail_send raises a question with POST /raise, the "dashboard" here reads it from
GET /events and answers with POST /response, and the tool call finishes. No Docker
and no network beyond 127.0.0.1. All addresses are made up.
"""

from pathlib import Path

import anyio
import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from core.firewall import core_client
from core.firewall.session import Sessions
from core.firewall.vault import Vault
from core.gateway import build_gateway
from tests.firewall.helpers import AS_OPENCLAW, make_world, mcp_request
from tests.seams import core_backend

pytestmark = pytest.mark.anyio
REAL_TO = "sam.rivera@example.com"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def core(monkeypatch):
    """C's back end on a free port; the gateway's core_client points at it."""
    url, notifications, server = core_backend.start()
    monkeypatch.setattr(core_client, "CORE_URL", url)
    yield url, notifications
    server.shutdown()


@pytest.fixture
def gateway(tmp_path):
    settings = make_world(tmp_path, tools=("gmail_send",))
    to = Vault(settings.state_dir / "gateway.db").placeholder("openclaw:run-1", "EMAIL", REAL_TO)
    return build_gateway(settings, sessions=Sessions()), settings, to


async def send(gateway, to: str) -> str:
    with mcp_request(AS_OPENCLAW):
        content = await gateway.call_tool("gmail_send", {"to": to, "subject": "Re: tools", "body": "Saturday works."})
    return content[0].text


def outbox(settings) -> list[Path]:
    return sorted((settings.state_dir / "outbox").glob("*.eml"))


async def test_send_waits_for_approval(core, gateway):
    url, _ = core
    app, settings, to = gateway
    result: dict = {}

    async def agent_sends():
        result["text"] = await send(app, to)

    async with anyio.create_task_group() as tasks:
        tasks.start_soon(agent_sends)
        raised = await anyio.to_thread.run_sync(core_backend.Dashboard(url).next)
        # The pop-up shows the real recipient; the agent is still waiting, nothing is sent yet.
        assert (raised["kind"], raised["container_id"], raised["tool"]) == ("approval", "openclaw", "gmail_send")
        assert raised["to"] == REAL_TO and REAL_TO in raised["question"]
        assert outbox(settings) == []
        assert await anyio.to_thread.run_sync(core_backend.answer, url, raised["request_id"], "approve") == 200
    assert result["text"] == f"Sent the email to {to}."
    assert len(outbox(settings)) == 1


async def test_no_answer_means_deny(core, gateway, monkeypatch):
    _, notifications = core
    app, settings, to = gateway
    # The back end gives the user 120 s; one second is enough to show what happens after.
    monkeypatch.setattr(notifications, "TIMEOUT_SECONDS", 1)
    with pytest.raises(ToolError, match="send_needs_approval"):
        await send(app, to)
    assert outbox(settings) == []


async def test_dead_back_end_means_deny(gateway, monkeypatch):
    app, settings, to = gateway
    # Nothing listens on port 9 (discard): the ask fails, and failing closed means no send.
    monkeypatch.setattr(core_client, "CORE_URL", "http://127.0.0.1:9")
    with pytest.raises(ToolError, match="send_needs_approval"):
        await send(app, to)
    assert outbox(settings) == []


async def test_consent_question_reaches_the_dashboard(core, tmp_path):
    """A model call holding Confidential file text raises kind "consent" with the file and provider."""
    url, _ = core
    settings = make_world(tmp_path, tools=("files_read",))
    app = build_gateway(settings, sessions=Sessions())  # mock model: nothing leaves the machine
    with mcp_request(AS_OPENCLAW):
        result = (await app.call_tool("files_read", {"path": "taxes/summary.txt"}))[0].text
    body = {
        "model": "gemini-flash-lite-latest",
        "messages": [
            {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": result},
        ],
    }
    transport = httpx.ASGITransport(app=app.streamable_http_app())
    async with anyio.create_task_group() as tasks:

        async def agent_calls_model():
            async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
                await client.post("/model/chat/completions", json=body, headers={"authorization": AS_OPENCLAW})

        tasks.start_soon(agent_calls_model)
        raised = await anyio.to_thread.run_sync(core_backend.Dashboard(url).next)
        assert (raised["kind"], raised["file"], raised["folder"], raised["provider"]) == (
            "consent", "taxes/summary.txt", "taxes", "Gemini"
        )
        assert await anyio.to_thread.run_sync(core_backend.answer, url, raised["request_id"], "deny") == 200

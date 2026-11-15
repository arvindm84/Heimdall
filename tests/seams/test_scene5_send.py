"""Scene 5 with real containers: OpenClaw replies to an email and the user approves the send.

C's back end runs on the host at port 8765, where the gateway container reaches it
(host.docker.internal:8765). The agent's tool calls are made with curl from inside
the OpenClaw container, so the test does not depend on what the model decides.
"""

import json
import re
import threading

import pytest

from agents import manager, testing
from agents.openclaw import agent as openclaw
from core.contracts.agents import AgentPermissions
from tests.seams import core_backend

REAL_TO = "priya.raman@example.com"


@pytest.fixture(scope="module")
def core():
    url, _, server = core_backend.start(port=8765)
    yield url, core_backend.Dashboard(url)
    server.shutdown()


@pytest.fixture(scope="module")
def opened(core):
    manager.open_agent("openclaw", AgentPermissions(tools=["gmail_read", "gmail_draft", "gmail_send"]))
    yield
    manager.kill_agent("openclaw")


def mcp_call(tool: str, arguments: dict) -> dict:
    """One MCP tools/call from inside the OpenClaw container. Returns the JSON-RPC result."""
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    reply = testing.in_agent(
        "openclaw",
        "curl", "-s", "-X", "POST", "http://gateway:8080/mcp",
        "-H", f"Authorization: Bearer {openclaw.FAKE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json, text/event-stream",
        "-d", json.dumps(request),
    )  # fmt: skip
    data = next(line.removeprefix("data: ") for line in reply.splitlines() if line.startswith("data: "))
    return json.loads(data)["result"]


def priya_placeholder() -> str:
    """Read Priya's email the way the agent does, and take her address's placeholder from it."""
    text = mcp_call("gmail_read", {"query": "Saturday tools"})["content"][0]["text"]
    assert REAL_TO not in text
    return re.search(r"From: .*?(\{\{EMAIL_\d+\}\})", text).group(1)


def sent_to_priya() -> int:
    """How many emails in the gateway's outbox go to Priya (the outbox is kept in a volume)."""
    script = (
        "import pathlib; print(sum('To: priya.raman@example.com' in p.read_text()"
        " for p in pathlib.Path('/state/outbox').glob('*.eml')))"
    )
    return int(manager.compose("exec", "-T", "gateway", "python", "-c", script).strip())


@pytest.mark.docker
def test_draft_keeps_the_placeholder_and_asks_nothing(opened):
    to = priya_placeholder()
    result = mcp_call("gmail_draft", {"to": to, "subject": "Re: Saturday tools", "body": "Saturday works."})
    assert not result.get("isError")
    assert result["content"][0]["text"] == f"Saved a draft to {to}."


@pytest.mark.docker
def test_reply_is_sent_once_after_approval_with_the_real_address(opened, core):
    url, dashboard = core
    to = priya_placeholder()
    before = sent_to_priya()
    result: dict = {}
    args = {"to": to, "subject": "Re: Saturday tools", "body": "Saturday works. Thanks!"}
    agent = threading.Thread(target=lambda: result.update(mcp_call("gmail_send", args)))
    agent.start()
    raised = dashboard.next()
    # The pop-up shows the real address; the agent only ever wrote the placeholder.
    assert raised["to"] == REAL_TO and REAL_TO in raised["question"]
    assert sent_to_priya() == before
    assert core_backend.answer(url, raised["request_id"], "approve") == 200
    agent.join(timeout=30)
    assert result["content"][0]["text"] == f"Sent the email to {to}."
    assert sent_to_priya() == before + 1
    # The gateway's log has the decision but never the real address.
    logs = manager.compose("logs", "--no-log-prefix", "gateway")
    assert REAL_TO not in logs
    send = [e for e in testing.gateway_log("tool_call", "openclaw") if e["tool"] == "gmail_send"][-1]
    assert (send["decision"], send["rule_id"], send["filled"]) == ("approved", "send_needs_approval", 1)


@pytest.mark.docker
def test_deny_sends_nothing(opened, core):
    url, dashboard = core
    to = priya_placeholder()
    before = sent_to_priya()
    result: dict = {}
    args = {"to": to, "subject": "Re: Saturday tools", "body": "Saturday works."}
    agent = threading.Thread(target=lambda: result.update(mcp_call("gmail_send", args)))
    agent.start()
    raised = dashboard.next()
    assert core_backend.answer(url, raised["request_id"], "deny") == 200
    agent.join(timeout=30)
    assert result["isError"] and "send_needs_approval" in result["content"][0]["text"]
    assert sent_to_priya() == before

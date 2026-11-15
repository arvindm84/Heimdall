"""Scene 6 with real containers: OpenClaw on Gemini reads a Confidential file; the user denies consent.

C's back end runs on the host at port 8765. The agent's turn uses the real model
(needs GEMINI_API_KEY in .env), so the model decides when to call files_read; the
checks are on what the gateway did, not on the model's wording. The tax file is made up.
"""

import threading

import pytest

from agents import manager, testing
from core.contracts.agents import AgentPermissions, FolderAccess
from tests.seams import core_backend

RETURN = "Made-up 2025 return for Jordan Lee.\nAdjusted gross income: 71,250.\nRefund due: 1,140.\n"


@pytest.fixture(scope="module")
def core():
    url, _, server = core_backend.start(port=8765)
    yield url, core_backend.Dashboard(url)
    server.shutdown()


@pytest.fixture(scope="module")
def opened(core, tmp_path_factory):
    taxes = tmp_path_factory.mktemp("scene6") / "taxes"
    taxes.mkdir()
    (taxes / "return.txt").write_text(RETURN, encoding="utf-8")
    folders = [FolderAccess(path=str(taxes), label="confidential")]
    manager.open_agent("openclaw", AgentPermissions(tools=["files_read"], folders=folders))
    yield
    manager.kill_agent("openclaw")


@pytest.mark.docker
def test_deny_sends_the_request_without_the_file_text(opened, core):
    url, dashboard = core
    withheld_before = len(testing.gateway_log("model_withheld", "openclaw"))
    forwarded_before = len(testing.gateway_log("model_forwarded", "openclaw"))
    reply: dict = {}
    ask = "Use files_read to read taxes/return.txt and tell me my refund."
    turn = threading.Thread(target=lambda: reply.update(text=testing.in_agent("openclaw", *testing.ASK["openclaw"](ask))))
    turn.start()
    raised = dashboard.next(timeout=150)
    assert (raised["kind"], raised["file"], raised["provider"]) == ("consent", "taxes/return.txt", "Gemini")
    assert core_backend.answer(url, raised["request_id"], "deny") == 200
    turn.join(timeout=200)
    print(reply.get("text"))
    withheld = testing.gateway_log("model_withheld", "openclaw")[withheld_before:]
    assert withheld and all(event["files"] == ["taxes/return.txt"] for event in withheld)
    # The request still went to Gemini (without the text), and the model never saw the refund.
    assert len(testing.gateway_log("model_forwarded", "openclaw")) > forwarded_before
    assert "1,140" not in reply.get("text", "")
    # One question for the whole turn: the deny is remembered for the session.
    assert [e["decision"] for e in testing.gateway_log("consent", "openclaw")][-1:] == ["deny"]

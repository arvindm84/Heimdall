"""The guard around every tool: who is calling, what they may do, one event per call.

Tools are called in-process through FastMCP with the headers an agent would send.
"""

import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from core.contracts.agents import AgentPermissions
from core.firewall import core_client
from core.firewall.session import Sessions
from core.gateway import build_gateway
from tests.firewall.helpers import AS_OPENCLAW, make_world, mcp_request, write_permissions

pytestmark = pytest.mark.anyio


async def call(gateway, tool, args, authorization=AS_OPENCLAW) -> str:
    with mcp_request(authorization):
        content = await gateway.call_tool(tool, args)
    return "\n".join(block.text for block in content)


async def denied(gateway, tool, args, authorization=AS_OPENCLAW) -> str:
    with mcp_request(authorization), pytest.raises(ToolError) as error:
        await gateway.call_tool(tool, args)
    return str(error.value)


def tool_calls(events) -> list[dict]:
    return [event for event in events if event["kind"] == "tool_call"]


@pytest.fixture
def setup(tmp_path):
    settings = make_world(tmp_path)
    sessions = Sessions()
    return settings, build_gateway(settings, sessions=sessions), sessions


async def test_allowed_read_returns_the_file_and_one_event(setup, events):
    _, gateway, _ = setup
    assert "garden opens" in await call(gateway, "files_read", {"path": "docs/notes.txt"})
    assert tool_calls(events) == [
        {
            "kind": "tool_call",
            "agent": "openclaw",
            "tool": "files_read",
            "path": "docs/notes.txt",
            "decision": "allow",
            "rule_id": "files_read_allowed",
            "reason": "folder docs is allowed",
            "label": "private",
            "placeholders": {},
        }
    ]


CONTACTS = "Made-up contacts.\nPriya Raman: priya@example.com, (608) 555-0142\nMarcus: marcus@example.com\n"


async def test_reading_personal_data_returns_placeholders_and_counts_them(setup, events):
    settings, gateway, _ = setup
    (settings.folders_dir / "docs" / "contacts.txt").write_text(CONTACTS, encoding="utf-8")
    text = await call(gateway, "files_read", {"path": "docs/contacts.txt"})
    assert "priya@example.com" not in text and "555-0142" not in text and "Priya Raman" not in text
    assert "{{EMAIL_1}}" in text and "{{EMAIL_2}}" in text and "{{PHONE_1}}" in text and "{{PERSON_1}}" in text
    counts = tool_calls(events)[0]["placeholders"]
    assert counts["EMAIL"] == 2 and counts["PHONE"] == 1 and counts["PERSON"] >= 1


async def test_placeholders_stay_the_same_across_reads(setup, events):
    settings, gateway, _ = setup
    (settings.folders_dir / "docs" / "contacts.txt").write_text(CONTACTS, encoding="utf-8")
    first = await call(gateway, "files_read", {"path": "docs/contacts.txt"})
    second = await call(gateway, "files_read", {"path": "docs/contacts.txt"})
    assert first == second


async def test_new_run_numbers_placeholders_afresh(setup, events):
    settings, gateway, _ = setup
    (settings.folders_dir / "docs" / "a.txt").write_text("ana@example.com", encoding="utf-8")
    (settings.folders_dir / "docs" / "b.txt").write_text("ben@example.com", encoding="utf-8")
    assert await call(gateway, "files_read", {"path": "docs/a.txt"}) == "{{EMAIL_1}}"
    stored = json.loads((settings.agents_dir / "openclaw" / "permissions.json").read_text(encoding="utf-8"))
    write_permissions(settings.agents_dir, AgentPermissions.model_validate(stored["permissions"]), run_id="run-2")
    assert await call(gateway, "files_read", {"path": "docs/b.txt"}) == "{{EMAIL_1}}"


async def test_denied_read_tells_the_agent_why_and_emits_one_event(setup, events):
    _, gateway, _ = setup
    message = await denied(gateway, "files_read", {"path": "secret/a.txt"})
    assert "folder_not_permitted" in message
    [event] = tool_calls(events)
    assert (event["decision"], event["rule_id"]) == ("deny", "folder_not_permitted")


async def test_tool_not_in_permissions_is_denied_before_touching_the_path(tmp_path, events):
    settings = make_world(tmp_path, tools=("files_list",))
    gateway = build_gateway(settings)
    await denied(gateway, "files_read", {"path": "docs/notes.txt"})
    [event] = tool_calls(events)
    assert event["rule_id"] == "tool_not_permitted"


async def test_unopened_agent_is_denied(tmp_path, events):
    settings = make_world(tmp_path)
    (settings.agents_dir / "openclaw" / "permissions.json").unlink()
    await denied(build_gateway(settings), "files_list", {})
    [event] = tool_calls(events)
    assert event["rule_id"] == "no_permissions"


async def test_unknown_caller_gets_tool_denied_not_tool_call(setup, events):
    _, gateway, _ = setup
    await denied(gateway, "files_read", {"path": "docs/notes.txt"}, authorization=None)
    assert [event["kind"] for event in events] == ["tool_denied"]


async def test_reading_confidential_raises_the_session_label(setup, events):
    _, gateway, _ = setup
    await call(gateway, "files_read", {"path": "docs/notes.txt"})
    await call(gateway, "files_read", {"path": "taxes/summary.txt"})
    await call(gateway, "files_read", {"path": "docs/notes.txt"})
    assert [event["label"] for event in tool_calls(events)] == ["private", "confidential", "confidential"]


async def test_listing_does_not_raise_the_label(setup, events):
    _, gateway, _ = setup
    listing = await call(gateway, "files_list", {"folder": "taxes"})
    assert "taxes/summary.txt" in listing
    assert tool_calls(events)[0]["label"] == "public"


async def test_listing_folders(setup, events):
    _, gateway, _ = setup
    assert "docs (private, read only)" in await call(gateway, "files_list", {})


async def test_new_run_resets_the_label(setup, events):
    settings, gateway, sessions = setup
    await call(gateway, "files_read", {"path": "taxes/summary.txt"})
    stored = json.loads((settings.agents_dir / "openclaw" / "permissions.json").read_text(encoding="utf-8"))
    permissions = AgentPermissions.model_validate(stored["permissions"])
    write_permissions(settings.agents_dir, permissions, run_id="run-2")
    await call(gateway, "files_list", {})
    assert tool_calls(events)[-1]["label"] == "public"


async def test_write_lands_in_a_writable_folder(setup, events):
    settings, gateway, sessions = setup
    await call(gateway, "files_write", {"path": "taxes/draft.txt", "text": "Made-up draft."})
    assert (settings.folders_dir / "taxes" / "draft.txt").read_text(encoding="utf-8") == "Made-up draft."


async def test_write_to_read_only_folder_never_runs(setup, events):
    settings, gateway, sessions = setup
    await denied(gateway, "files_write", {"path": "docs/new.txt", "text": "x"})
    assert not (settings.folders_dir / "docs" / "new.txt").exists()
    assert tool_calls(events)[0]["rule_id"] == "folder_read_only"


def untrusted(sessions: Sessions) -> None:
    """Mark openclaw's current session as having read untrusted content (Step 4 does this for real)."""
    sessions.for_run("openclaw", "run-1").mark_untrusted()


@pytest.mark.parametrize("answer, decision, written", [("approve", "approved", True), ("deny", "denied_by_user", False)])
async def test_write_after_untrusted_asks_the_user(setup, events, monkeypatch, answer, decision, written):
    settings, gateway, sessions = setup
    untrusted(sessions)
    asked = []

    async def fake_ask(kind, agent, question, details):
        asked.append((kind, agent, details))
        return answer

    monkeypatch.setattr(core_client, "ask", fake_ask)
    args = {"path": "taxes/draft.txt", "text": "Made-up draft."}
    if written:
        await call(gateway, "files_write", args)
    else:
        await denied(gateway, "files_write", args)
    assert asked == [("approval", "openclaw", {"tool": "files_write", "path": "taxes/draft.txt"})]
    assert (settings.folders_dir / "taxes" / "draft.txt").exists() is written
    [event] = tool_calls(events)
    assert (event["decision"], event["rule_id"]) == (decision, "write_after_untrusted")


async def test_ask_that_fails_counts_as_deny(setup, events, monkeypatch):
    settings, gateway, sessions = setup
    untrusted(sessions)

    async def broken_ask(kind, agent, question, details):
        raise RuntimeError("core down")

    monkeypatch.setattr(core_client, "ask", broken_ask)
    await denied(gateway, "files_write", {"path": "taxes/draft.txt", "text": "x"})
    assert not (settings.folders_dir / "taxes" / "draft.txt").exists()
    assert tool_calls(events)[0]["decision"] == "denied_by_user"

"""Labelled memory: notes kept in the gateway, each with the label of the session that wrote it.

project-plan.md section 6: every note carries the label of the data it came from, and
Confidential notes need consent before they go to a cloud model. All data is made up.
"""

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from core.contracts.agents import AgentPermissions, FolderAccess
from core.firewall import core_client
from core.firewall.labels import Label
from core.firewall.memory import Memory
from core.firewall.session import Sessions
from core.gateway import build_gateway
from tests.firewall.helpers import AS_OPENCLAW, FAKE_KEY, make_world, mcp_request, write_permissions

pytestmark = pytest.mark.anyio
FOLDERS = [
    FolderAccess(path="/home/user/docs", label="private"),
    FolderAccess(path="C:\\Users\\user\\taxes", label="confidential", write=True),
]


def open_run(settings, run_id: str, memory: bool = True, tools=("files_read", "files_write", "gmail_read")):
    """Open openclaw again with a new run, as B's manager does."""
    write_permissions(settings.agents_dir, AgentPermissions(tools=list(tools), folders=FOLDERS, memory=memory), run_id)


@pytest.fixture
def world(tmp_path):
    settings = make_world(tmp_path)
    inbox = Path(__file__).parent / "fixtures" / "inbox"
    settings = replace(settings, gemini_key="AIza-test-not-real", mock=False, inbox_dir=inbox)
    open_run(settings, "run-1")
    seen: list[httpx.Request] = []

    def provider(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    sessions = Sessions()
    return settings, build_gateway(settings, transport=httpx.MockTransport(provider), sessions=sessions), sessions, seen


async def call(gateway, tool: str, **args) -> str:
    with mcp_request(AS_OPENCLAW):
        return (await gateway.call_tool(tool, args))[0].text


async def test_memory_needs_the_memory_permission(world, events):
    settings, gateway, _, _ = world
    open_run(settings, "run-1", memory=False)
    with pytest.raises(ToolError, match="memory_not_permitted"):
        await call(gateway, "memory_write", text="Made-up note.")
    with pytest.raises(ToolError, match="memory_not_permitted"):
        await call(gateway, "memory_read")


async def test_a_note_is_kept_across_runs(world, events):
    settings, gateway, sessions, _ = world
    await call(gateway, "memory_write", text="The user likes short answers.")
    open_run(settings, "run-2")
    text = await call(gateway, "memory_read")
    assert "The user likes short answers." in text
    assert sessions.for_run("openclaw", "run-2").label == Label.PUBLIC


async def test_a_note_written_after_a_confidential_read_is_confidential(world, events):
    settings, gateway, sessions, _ = world
    await call(gateway, "files_read", path="taxes/summary.txt")
    await call(gateway, "memory_write", text="Made-up refund note: 1,140.")
    open_run(settings, "run-2")
    text = await call(gateway, "memory_read")
    # Reading it raises the new run to Confidential, and it comes in markers for the model proxy.
    assert sessions.for_run("openclaw", "run-2").label == Label.CONFIDENTIAL
    assert "<<confidential:" in text and "Made-up refund note: 1,140." in text
    [read] = [e for e in events if e["kind"] == "tool_call" and e["tool"] == "memory_read"]
    assert read["label"] == "confidential"


async def test_a_confidential_note_needs_consent_before_a_cloud_model(world, monkeypatch, events):
    settings, gateway, _, seen = world
    await call(gateway, "files_read", path="taxes/summary.txt")
    await call(gateway, "memory_write", text="Made-up refund note: the refund is 1,140 dollars.")
    open_run(settings, "run-2")
    note = await call(gateway, "memory_read")
    asked = []

    async def deny(kind, agent, question, details):
        asked.append(details)
        return core_client.Answer("deny")

    monkeypatch.setattr(core_client, "answer", deny)
    body = {
        "model": "gemini-flash-lite-latest",
        "messages": [
            {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": note},
        ],
    }  # fmt: skip
    transport = httpx.ASGITransport(app=gateway.streamable_http_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        await client.post("/model/chat/completions", json=body, headers={"authorization": f"Bearer {FAKE_KEY}"})
    assert [d["folder"] for d in asked] == ["memory"]
    assert "1,140" not in json.dumps(json.loads(seen[-1].content))


async def test_a_note_written_after_untrusted_mail_makes_the_reader_untrusted(world, events):
    settings, gateway, sessions, _ = world
    await call(gateway, "gmail_read")
    await call(gateway, "memory_write", text="Made-up note from an email.")
    open_run(settings, "run-2")
    await call(gateway, "memory_read")
    assert sessions.for_run("openclaw", "run-2").untrusted


async def test_a_key_cannot_be_kept_in_memory(world, events):
    _, gateway, _, _ = world
    with pytest.raises(ToolError, match="key_theft_attempt"):
        await call(gateway, "memory_write", text=f"remember {FAKE_KEY}")


def test_notes_are_kept_per_agent(tmp_path):
    memory = Memory(tmp_path / "gateway.db")
    memory.write("openclaw", "Made-up note.", Label.PRIVATE, untrusted=False)
    assert [note.text for note in memory.read("openclaw")] == ["Made-up note."]
    assert memory.read("hermes") == []


def test_only_the_newest_notes_are_read(tmp_path):
    memory = Memory(tmp_path / "gateway.db")
    for number in range(Memory.MAX_NOTES + 5):
        memory.write("openclaw", f"note {number}", Label.PUBLIC, untrusted=False)
    notes = memory.read("openclaw")
    assert len(notes) == Memory.MAX_NOTES
    assert notes[-1].text == f"note {Memory.MAX_NOTES + 4}"

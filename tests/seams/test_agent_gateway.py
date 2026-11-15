"""Seam 1 (B and A): agent container -> gateway, with real containers and a real folder.

Most checks send MCP calls with curl from inside the OpenClaw container, so they
use the agent's network, its key and the folder mount B's manager sets up, without
depending on what the model decides to do. One check lets the model read the file
itself (needs GEMINI_API_KEY in .env).
"""

import json

import pytest

from agents import manager, testing
from agents.openclaw import agent as openclaw
from core.contracts.agents import AgentPermissions, FolderAccess

NOTE = "Made-up seam note: the blue folder is in the hall closet."
CONTACTS = "Made-up contacts. Priya Raman: priya@example.com, (608) 555-0142."


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    """Open OpenClaw with one made-up private folder; yield its name as the agent sees it."""
    docs = tmp_path_factory.mktemp("seam") / "seamdocs"
    docs.mkdir()
    (docs / "notes.txt").write_text(NOTE, encoding="utf-8")
    (docs / "contacts.txt").write_text(CONTACTS, encoding="utf-8")
    permissions = AgentPermissions(
        tools=["files_list", "files_read"], folders=[FolderAccess(path=str(docs), label="private")]
    )
    manager.open_agent("openclaw", permissions)
    yield docs.name
    manager.kill_agent("openclaw")


def mcp_call(tool: str, arguments: dict, key: str = openclaw.FAKE_KEY) -> dict:
    """One MCP tools/call from inside the OpenClaw container. Returns the JSON-RPC result."""
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    reply = testing.in_agent(
        "openclaw",
        "curl", "-s", "-X", "POST", "http://gateway:8080/mcp",
        "-H", f"Authorization: Bearer {key}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json, text/event-stream",
        "-d", json.dumps(request),
    )  # fmt: skip
    data = next(line.removeprefix("data: ") for line in reply.splitlines() if line.startswith("data: "))
    return json.loads(data)["result"]


def last_tool_call() -> dict:
    return testing.gateway_log("tool_call", "openclaw")[-1]


@pytest.mark.docker
def test_agent_reads_a_file_in_its_folder(folder):
    result = mcp_call("files_read", {"path": f"{folder}/notes.txt"})
    assert not result.get("isError")
    assert result["content"][0]["text"] == NOTE
    event = last_tool_call()
    assert (event["decision"], event["rule_id"], event["label"]) == ("allow", "files_read_allowed", "private")


@pytest.mark.docker
def test_agent_lists_its_folder(folder):
    result = mcp_call("files_list", {"folder": folder})
    assert result["content"][0]["text"].splitlines() == [f"{folder}/contacts.txt", f"{folder}/notes.txt"]


@pytest.mark.docker
def test_personal_data_reaches_the_agent_only_as_placeholders(folder):
    text = mcp_call("files_read", {"path": f"{folder}/contacts.txt"})["content"][0]["text"]
    assert "priya@example.com" not in text and "555-0142" not in text and "Priya" not in text
    assert "{{EMAIL_1}}" in text and "{{PHONE_1}}" in text and "{{PERSON_1}}" in text
    assert last_tool_call()["placeholders"] == {"PERSON": 1, "EMAIL": 1, "PHONE": 1}


@pytest.mark.docker
def test_path_outside_the_folder_is_denied(folder):
    result = mcp_call("files_read", {"path": f"{folder}/../../../config/agents/openclaw/permissions.json"})
    assert result["isError"]
    assert last_tool_call()["rule_id"] == "path_escapes_folder"


@pytest.mark.docker
def test_folder_not_granted_is_denied(folder):
    result = mcp_call("files_read", {"path": "secret/passwords.txt"})
    assert result["isError"]
    assert last_tool_call()["rule_id"] == "folder_not_permitted"


@pytest.mark.docker
def test_tool_not_granted_is_denied(folder):
    result = mcp_call("files_write", {"path": f"{folder}/x.txt", "text": "x"})
    assert result["isError"]
    assert last_tool_call()["rule_id"] == "tool_not_permitted"


@pytest.mark.docker
def test_another_agents_key_is_refused(folder):
    # Hermes's key is known to the gateway, but Hermes has no permissions.json in this run
    # (or one for its own folders): it cannot read OpenClaw's folder.
    result = mcp_call("files_read", {"path": f"{folder}/notes.txt"}, key="sk-fake-hermes-01")
    assert result["isError"]


@pytest.mark.docker
def test_model_reads_the_file_through_the_gateway(folder):
    before = len(testing.gateway_log("tool_call", "openclaw"))
    testing.ask("openclaw", f"Use files_read to read {folder}/notes.txt and tell me what it says.")
    reads = [
        event
        for event in testing.gateway_log("tool_call", "openclaw")[before:]
        if event["tool"] == "files_read" and event["decision"] == "allow"
    ]
    assert reads, "the model never read the file through the gateway"

import json

import pytest

from agents import manager, testing
from agents.openclaw import agent
from core.contracts.agents import AgentPermissions, FolderAccess


def test_config_offers_only_permitted_tools():
    config = agent.build_config(AgentPermissions(tools=["files_read"]), "gemini", testing.MODEL)
    assert config["tools"]["alsoAllow"] == ["heimdall__files_read"]
    assert config["tools"]["profile"] == "minimal"


def test_config_calls_the_gateway_with_only_the_fake_key():
    config = agent.build_config(AgentPermissions(), "gemini", testing.MODEL)
    entry = config["models"]["providers"]["heimdall"]
    assert entry["baseUrl"] == "http://gateway:8080/model"
    assert entry["api"] == "openai-completions"
    assert entry["apiKey"] == agent.FAKE_KEY
    assert entry["models"][0]["id"] == testing.MODEL
    server = config["mcp"]["servers"]["heimdall"]
    assert server["url"] == "http://gateway:8080/mcp"
    assert server["headers"]["Authorization"] == f"Bearer {agent.FAKE_KEY}"


def test_memory_and_delegation_are_refused():
    with pytest.raises(ValueError):
        agent.build_config(AgentPermissions(memory=True), "gemini", testing.MODEL)
    with pytest.raises(ValueError):
        agent.build_config(AgentPermissions(delegation=True), "gemini", testing.MODEL)


@pytest.fixture(scope="module")
def opened():
    yield manager.open_agent("openclaw", AgentPermissions(tools=["files_read"]))
    manager.kill_agent("openclaw")


@pytest.mark.docker
def test_sealed_and_routed_through_the_gateway(opened):
    testing.check_sealed_and_routed("openclaw", opened)


@pytest.mark.docker
def test_model_is_offered_only_permitted_tools(opened):
    calls = [call for call in testing.ask("openclaw", "Say hi") if call["tools_offered"]]
    assert calls
    assert all(call["tools_offered"] == ["heimdall__files_read"] for call in calls)


@pytest.mark.docker
def test_kill_switch_takes_the_chat_down(opened):
    manager.kill_agent("openclaw")
    assert manager.chat_status(opened.chat_url, opened.chat_token) is None


@pytest.mark.docker
def test_staged_skill_and_mounted_folder_work_in_container(tmp_path):
    readings = tmp_path / "Readings"
    readings.mkdir()
    (readings / "essay.txt").write_text("Main argument: capability security seals agents.", encoding="utf-8")
    permissions = AgentPermissions(
        tools=["files_list", "files_read"],
        folders=[FolderAccess(path=str(readings), label="private")],
        skills=["reading-brief"],
    )
    manager.open_agent("openclaw", permissions)
    try:
        skill_text = testing.in_agent("openclaw", "cat", "/home/node/.openclaw/workspace/skills/reading-brief/SKILL.md")
        assert "Reading brief" in skill_text
        # Quarantined skill is never inside the container.
        quarantined_check = testing.in_agent(
            "openclaw", "sh", "-c", "test ! -e /home/node/.openclaw/workspace/skills/weather-helper && echo clean"
        )
        assert quarantined_check.strip() == "clean"
    finally:
        manager.kill_agent("openclaw")


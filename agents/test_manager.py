import pytest

from agents import manager
from agents.permissions import AgentPermissions, FolderAccess


def test_gateway_config_lists_each_agent_and_keeps_the_others():
    folder = FolderAccess(path="C:/docs", label="confidential")
    first = manager.build_gateway_config({}, "openclaw", AgentPermissions(tools=["files_read"]), "gemini")
    both = manager.build_gateway_config(first, "hermes", AgentPermissions(folders=[folder]), "gemini")
    assert [entry["name"] for entry in both["agents"]] == ["openclaw", "hermes"]
    assert both["agents"][0] == {
        "name": "openclaw",
        "fake_key": "sk-fake-openclaw-01",
        "folders": [],
        "tools": ["files_read"],
        "provider": "gemini",
    }
    assert both["folders"] == [{"path": "C:/docs", "label": "confidential", "writable": False}]
    assert "generativelanguage.googleapis.com" in both["providers"]["allow"]


def test_unknown_agent_and_provider_are_rejected():
    with pytest.raises(ValueError):
        manager.stop_agent("not-an-agent")
    with pytest.raises(ValueError):
        manager.open_agent("openclaw", AgentPermissions(), "not-a-provider")

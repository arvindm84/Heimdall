import pytest

from pathlib import Path

from agents import manager, skills
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
        "skills": [],
        "provider": "gemini",
    }
    assert both["folders"] == [{"path": "C:/docs", "label": "confidential", "writable": False}]
    assert "generativelanguage.googleapis.com" in both["providers"]["allow"]


def test_unknown_agent_and_provider_are_rejected():
    with pytest.raises(ValueError):
        manager.stop_agent("not-an-agent")
    with pytest.raises(ValueError):
        manager.open_agent("openclaw", AgentPermissions(), "not-a-provider")


def test_malicious_demo_skill_is_quarantined_and_clean_skill_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(skills, "QUARANTINE", tmp_path / "skills" / "quarantine")
    bad = skills.install("openclaw", Path(__file__).parent / "openclaw" / "demo-skills" / "weather-helper")
    assert bad["status"] == "quarantined"
    assert {f["rule"] for f in bad["findings"]} >= {"reads a secrets file", "sends data out"}
    good = tmp_path / "src" / "haiku"
    good.mkdir(parents=True)
    (good / "SKILL.md").write_text("---\nname: haiku\n---\nAnswer in a haiku.\n")
    assert skills.install("openclaw", good)["status"] == "installed"
    assert skills.installed("openclaw") == ["haiku"]
    with pytest.raises(ValueError):
        skills.stage("openclaw", ["weather-helper"])

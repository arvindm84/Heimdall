import json

import pytest

from pathlib import Path

from agents import manager, skills
from core.contracts.agents import AgentPermissions, FolderAccess


def test_permissions_json_and_folder_mounts_are_written_for_the_gateway(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setattr(manager, "FOLDER_MOUNTS", tmp_path / "gateway" / "compose.folders.yaml")
    docs, taxes = tmp_path / "docs", tmp_path / "taxes"
    docs.mkdir()
    taxes.mkdir()
    manager.write_permissions("openclaw", AgentPermissions(folders=[FolderAccess(path=str(docs))]))
    permissions = AgentPermissions(tools=["files_read"], folders=[FolderAccess(path=str(taxes), write=True)])
    manager.write_permissions("hermes", permissions)
    written = json.loads((tmp_path / "agents" / "hermes" / "permissions.json").read_text())
    assert written["fake_key"] == "sk-fake-hermes-01"
    stored_taxes = FolderAccess(path=str(taxes.resolve()), write=True)
    assert written["permissions"] == permissions.model_copy(update={"folders": [stored_taxes]}).model_dump()
    assert "provider" not in written and "model" not in written
    manager.write_permissions("hermes", permissions, "anthropic", "claude-haiku-4-5")
    again = json.loads((tmp_path / "agents" / "hermes" / "permissions.json").read_text())
    assert again["run_id"] != written["run_id"]
    # The gateway refuses model calls to any other provider or model.
    assert (again["provider"], again["model"]) == ("anthropic", "claude-haiku-4-5")
    mounts = json.loads(manager.FOLDER_MOUNTS.read_text())["services"]["gateway"]["volumes"]
    assert mounts == [
        {"type": "bind", "source": str(docs.resolve()), "target": "/data/folders/docs", "read_only": True},
        {"type": "bind", "source": str(taxes.resolve()), "target": "/data/folders/taxes", "read_only": False},
    ]
    manager.write_permissions("hermes", permissions, provider="anthropic")
    assert json.loads((tmp_path / "agents" / "hermes" / "permissions.json").read_text())["provider"] == "anthropic"


def test_relative_folder_is_stored_under_its_mount_name(tmp_path, monkeypatch):
    # The gateway finds a folder by the last part of its stored path, which must be
    # the name it is mounted under; "." alone would not tell it which folder.
    monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setattr(manager, "FOLDER_MOUNTS", tmp_path / "gateway" / "compose.folders.yaml")
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(tmp_path / "docs")
    manager.write_permissions("openclaw", AgentPermissions(folders=[FolderAccess(path=".")]))
    written = json.loads((tmp_path / "agents" / "openclaw" / "permissions.json").read_text())
    stored = Path(written["permissions"]["folders"][0]["path"])
    mount = json.loads(manager.FOLDER_MOUNTS.read_text())["services"]["gateway"]["volumes"][0]
    assert stored.is_absolute()
    assert mount["target"] == f"/data/folders/{stored.name}"


def test_another_agents_deleted_folder_does_not_block_opening(tmp_path, monkeypatch):
    # A folder granted to openclaw earlier was deleted since; hermes must still open.
    monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setattr(manager, "FOLDER_MOUNTS", tmp_path / "gateway" / "compose.folders.yaml")
    gone = tmp_path / "gone"
    gone.mkdir()
    manager.write_permissions("openclaw", AgentPermissions(folders=[FolderAccess(path=str(gone))]))
    gone.rmdir()
    manager.write_permissions("hermes", AgentPermissions(tools=["files_read"]))
    assert json.loads(manager.FOLDER_MOUNTS.read_text())["services"]["gateway"]["volumes"] == []


def test_folders_must_exist_and_have_different_names(tmp_path):
    (tmp_path / "a" / "docs").mkdir(parents=True)
    (tmp_path / "b" / "docs").mkdir(parents=True)
    clash = [FolderAccess(path=str(tmp_path / "a" / "docs")), FolderAccess(path=str(tmp_path / "b" / "docs"))]
    with pytest.raises(ValueError):
        manager.gateway_folder_mounts([AgentPermissions(folders=clash)])
    with pytest.raises(ValueError):
        manager.gateway_folder_mounts([AgentPermissions(folders=[FolderAccess(path=str(tmp_path / "missing"))])])


def test_unknown_agent_and_provider_are_rejected():
    with pytest.raises(ValueError):
        manager.stop_agent("not-an-agent")
    with pytest.raises(ValueError):
        manager.open_agent("openclaw", AgentPermissions(), "not-a-provider")


def test_malicious_demo_skill_is_quarantined_and_clean_skill_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(skills, "QUARANTINE", tmp_path / "skills" / "quarantine")
    results = {r["name"]: r for r in skills.sync_defaults("openclaw")}
    assert results["weather-helper"]["status"] == "quarantined"
    assert {f["rule"] for f in results["weather-helper"]["findings"]} >= {"reads a secrets file", "sends data out"}
    assert results["reading-brief"]["status"] == "installed"
    assert skills.installed("openclaw") == ["reading-brief"]
    assert [q["name"] for q in skills.quarantined()] == ["weather-helper"]
    staged = skills.stage("openclaw", ["reading-brief"])
    assert (staged / "reading-brief" / "SKILL.md").is_file()
    with pytest.raises(ValueError):
        skills.stage("openclaw", ["weather-helper"])


def test_a_refused_launch_leaves_the_running_agents_permissions_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path / "agents")
    monkeypatch.setattr(manager, "FOLDER_MOUNTS", tmp_path / "gateway" / "compose.folders.yaml")
    monkeypatch.setattr(skills, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(skills, "QUARANTINE", tmp_path / "skills" / "quarantine")
    monkeypatch.setattr(manager, "compose", lambda *args, **kwargs: pytest.fail("docker compose was run"))
    manager.write_permissions("openclaw", AgentPermissions(tools=["files_read"]))
    stored = tmp_path / "agents" / "openclaw" / "permissions.json"
    before = stored.read_text(encoding="utf-8")

    # weather-helper is quarantined by the scan, so it can't be given to the agent.
    with pytest.raises(ValueError, match="not installed"):
        manager.open_agent("openclaw", AgentPermissions(skills=["weather-helper"]))

    assert stored.read_text(encoding="utf-8") == before
    assert not (tmp_path / "agents" / "openclaw" / "config.json").exists()

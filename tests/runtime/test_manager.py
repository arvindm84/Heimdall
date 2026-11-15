import json
import subprocess

import pytest

from core.contracts.agents import AgentPermissions
from core.runtime import manager


def test_config_offers_only_permitted_tools():
    config = manager.build_config(AgentPermissions(tools=["files_read"]))
    assert config["tools"]["alsoAllow"] == ["heimdall__files_read"]
    assert config["tools"]["profile"] == "minimal"


def test_unknown_agent_is_rejected():
    with pytest.raises(ValueError):
        manager.stop_agent("not-an-agent")


def _in_agent(*command: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "openclaw", *command],
        cwd=manager.ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result.stdout + result.stderr


def _last_model_call() -> dict:
    logs = subprocess.run(
        ["docker", "compose", "logs", "--no-log-prefix", "gateway"],
        cwd=manager.ROOT,
        capture_output=True,
        text=True,
    ).stdout
    calls = [json.loads(line) for line in logs.splitlines() if line.startswith('{"kind": "model_call"')]
    return calls[-1]


@pytest.fixture(scope="module")
def opened():
    agent = manager.open_agent("openclaw", AgentPermissions(tools=["files_read"]))
    yield agent
    manager.kill_agent("openclaw")


@pytest.mark.docker
def test_chat_needs_the_token(opened):
    assert manager.chat_status(opened.chat_token) == 200
    assert manager.chat_status("wrong-token") == 401


@pytest.mark.docker
def test_agent_has_no_internet(opened):
    script = (
        "fetch('https://example.com',{signal:AbortSignal.timeout(6000)})"
        ".then(()=>console.log('REACHED')).catch(()=>console.log('BLOCKED'))"
    )
    assert "BLOCKED" in _in_agent("node", "-e", script)


@pytest.mark.docker
def test_agent_is_offered_only_permitted_tools_and_fake_key(opened):
    _in_agent("node", "openclaw.mjs", "agent", "--agent", "main", "-m", "Read my notes file", "--timeout", "120")
    call = _last_model_call()
    assert call["tools_offered"] == ["heimdall__files_read"]
    assert call["api_key"] == "sk-fake-openclaw-01"


@pytest.mark.docker
def test_kill_switch_takes_the_chat_down(opened):
    manager.kill_agent("openclaw")
    assert manager.chat_status(opened.chat_token) is None

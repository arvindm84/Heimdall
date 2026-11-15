import pytest

from agents import manager, testing
from agents.hermes import agent
from core.contracts.agents import AgentPermissions

META_TOOLS = {"tool_search", "tool_describe", "tool_call"}


def test_config_has_no_builtin_toolsets_by_default():
    config = agent.build_config(AgentPermissions(tools=["files_read"]), "gemini", testing.MODEL)
    assert config["platform_toolsets"]["cli"] == []
    assert config["memory"]["memory_enabled"] is False
    assert config["mcp_servers"]["heimdall"]["tools"]["include"] == ["files_read"]


def test_config_names_the_provider_and_sends_only_the_fake_key():
    config = agent.build_config(AgentPermissions(), "gemini", testing.MODEL)
    assert config["model"] == {"default": testing.MODEL, "provider": "gemini"}
    server = config["mcp_servers"]["heimdall"]
    assert server["url"] == "http://gateway:8080/mcp"
    assert server["headers"]["Authorization"] == f"Bearer {agent.FAKE_KEY}"
    assert config["telemetry"]["shared_metrics"] == {"enabled": False, "send": False, "offer_version": 2}


def test_local_model_is_an_openai_style_endpoint_on_the_gateway():
    model = manager.PROVIDERS["local"]
    config = agent.build_config(AgentPermissions(), "local", model)
    assert config["model"] == {
        "default": model,
        "provider": "custom",
        "base_url": "http://gateway:8080/model/local",
        "api_key": agent.FAKE_KEY,
    }


def test_memory_and_delegation_are_added_when_permitted():
    config = agent.build_config(AgentPermissions(memory=True, delegation=True), "gemini", testing.MODEL)
    assert config["platform_toolsets"]["cli"] == ["memory", "delegation"]
    assert config["memory"]["memory_enabled"] is True


@pytest.fixture(scope="module")
def opened():
    yield manager.open_agent("hermes", AgentPermissions(tools=["files_read"]))
    manager.kill_agent("hermes")


@pytest.mark.docker
def test_sealed_and_routed_through_the_gateway(opened):
    testing.check_sealed_and_routed("hermes", opened)


@pytest.mark.docker
def test_model_is_offered_no_builtin_tools(opened):
    calls = [call for call in testing.ask("hermes", "Say hi") if call["tools_offered"]]
    assert calls
    assert all(set(call["tools_offered"]) <= META_TOOLS for call in calls)
    listing = testing.in_agent("hermes", "hermes", "tools", "list")
    assert "include only: files_read" in listing
    assert "enabled" not in listing.replace("disabled", "")


@pytest.mark.docker
def test_kill_switch_takes_the_chat_down(opened):
    manager.kill_agent("hermes")
    assert manager.chat_status(opened.chat_url, opened.chat_token) is None


@pytest.mark.docker
def test_delegation_and_memory_are_offered_when_permitted():
    manager.open_agent("hermes", AgentPermissions(tools=["files_read"], memory=True, delegation=True))
    try:
        calls = [call for call in testing.ask("hermes", "Say hi") if call["tools_offered"]]
        assert {"delegate_task", "memory"} <= set(calls[-1]["tools_offered"])
    finally:
        manager.kill_agent("hermes")

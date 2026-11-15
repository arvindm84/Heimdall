import pytest

from agents import manager, testing
from agents.openclaw import agent
from core.contracts.agents import AgentPermissions


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


def test_local_model_goes_to_the_gateways_local_route():
    config = agent.build_config(AgentPermissions(), "local", manager.PROVIDERS["local"])
    entry = config["models"]["providers"]["heimdall"]
    assert entry["baseUrl"] == "http://gateway:8080/model/local"
    assert entry["api"] == "openai-completions"
    assert entry["apiKey"] == agent.FAKE_KEY


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

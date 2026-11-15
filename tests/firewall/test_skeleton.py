"""The MCP tools: canned text, one event per call, and no answer for unknown callers.

Tools are called in-process through FastMCP. `mcp_request` supplies the HTTP
headers an agent would send.
"""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from core.gateway import build_gateway
from tests.firewall.helpers import FAKE_KEY, mcp_request

pytestmark = pytest.mark.anyio
AS_OPENCLAW = f"Bearer {FAKE_KEY}"


async def test_files_read_returns_canned_text(mock_settings, events):
    gateway = build_gateway(mock_settings)
    with mcp_request(AS_OPENCLAW):
        content = await gateway.call_tool("files_read", {"path": "notes.txt"})
    assert "{{EMAIL_1}}" in content[0].text


async def test_files_read_sends_the_text_once(mock_settings, events):
    # No second, structured copy: agents would show the model the text twice.
    gateway = build_gateway(mock_settings)
    with mcp_request(AS_OPENCLAW):
        content = await gateway.call_tool("files_read", {"path": "notes.txt"})
    assert len(content) == 1


async def test_files_read_emits_event_naming_the_agent(mock_settings, events):
    gateway = build_gateway(mock_settings)
    with mcp_request(AS_OPENCLAW):
        await gateway.call_tool("files_read", {"path": "notes.txt"})
    assert events == [{"kind": "tool_call", "agent": "openclaw", "tool": "files_read", "path": "notes.txt"}]


async def test_files_list_names_the_canned_file(mock_settings, events):
    gateway = build_gateway(mock_settings)
    with mcp_request(AS_OPENCLAW):
        content = await gateway.call_tool("files_list", {})
    assert [block.text for block in content] == ["notes.txt"]


@pytest.mark.parametrize("authorization", [None, "Bearer sk-fake-someone-else-01", "Bearer "])
async def test_unknown_caller_is_denied_and_tool_does_not_run(mock_settings, events, authorization):
    gateway = build_gateway(mock_settings)
    with mcp_request(authorization), pytest.raises(ToolError):
        await gateway.call_tool("files_read", {"path": "notes.txt"})
    assert [event["kind"] for event in events] == ["tool_denied"]


async def test_call_with_no_http_request_is_denied(mock_settings, events):
    gateway = build_gateway(mock_settings)
    with pytest.raises(ToolError):
        await gateway.call_tool("files_read", {"path": "notes.txt"})


async def test_tools_use_underscore_names(mock_settings):
    # The Claude API rejects dots in tool names, so files.read would break agents.
    gateway = build_gateway(mock_settings)
    names = {tool.name for tool in await gateway.list_tools()}
    assert names == {"files_read", "files_list"}

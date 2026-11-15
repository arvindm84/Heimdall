"""Step 0: the MCP tools answer with canned text and emit one event per call.

Tools are called in-process through FastMCP, so there is no HTTP request and the
caller shows as "unknown". The bearer-header path was checked over real HTTP.
"""

import pytest

from core.gateway import build_gateway

pytestmark = pytest.mark.anyio


async def test_files_read_returns_canned_text(mock_settings, events):
    gateway = build_gateway(mock_settings)
    content, _ = await gateway.call_tool("files_read", {"path": "notes.txt"})
    assert "{{EMAIL_1}}" in content[0].text


async def test_files_read_emits_event(mock_settings, events):
    gateway = build_gateway(mock_settings)
    await gateway.call_tool("files_read", {"path": "notes.txt"})
    assert events == [{"kind": "tool_call", "agent": "unknown", "tool": "files_read", "path": "notes.txt"}]


async def test_files_list_names_the_canned_file(mock_settings, events):
    gateway = build_gateway(mock_settings)
    # A list return value comes back as structured output under "result".
    _, structured = await gateway.call_tool("files_list", {})
    assert structured == {"result": ["notes.txt"]}


async def test_tools_use_underscore_names(mock_settings):
    # The Claude API rejects dots in tool names, so files.read would break agents.
    gateway = build_gateway(mock_settings)
    names = {tool.name for tool in await gateway.list_tools()}
    assert names == {"files_read", "files_list"}

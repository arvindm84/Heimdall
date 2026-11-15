"""Gateway-wide tool rules: names, unknown callers, one copy of each result.

Tools are called in-process through FastMCP. `mcp_request` supplies the HTTP
headers an agent would send.
"""

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from core.gateway import build_gateway
from tests.firewall.helpers import AS_OPENCLAW, make_world, mcp_request

pytestmark = pytest.mark.anyio


async def test_files_read_sends_the_text_once(tmp_path, events):
    # No second, structured copy: agents would show the model the text twice.
    gateway = build_gateway(make_world(tmp_path))
    with mcp_request(AS_OPENCLAW):
        content = await gateway.call_tool("files_read", {"path": "docs/notes.txt"})
    assert len(content) == 1


@pytest.mark.parametrize("authorization", [None, "Bearer sk-fake-someone-else-01", "Bearer "])
async def test_unknown_caller_is_denied_and_tool_does_not_run(tmp_path, events, authorization):
    gateway = build_gateway(make_world(tmp_path))
    with mcp_request(authorization), pytest.raises(ToolError):
        await gateway.call_tool("files_read", {"path": "docs/notes.txt"})
    assert [event["kind"] for event in events] == ["tool_denied"]


async def test_call_with_no_http_request_is_denied(tmp_path, events):
    gateway = build_gateway(make_world(tmp_path))
    with pytest.raises(ToolError):
        await gateway.call_tool("files_read", {"path": "docs/notes.txt"})


async def test_tools_use_underscore_names(mock_settings):
    # The Claude API rejects dots in tool names, so files.read would break agents.
    gateway = build_gateway(mock_settings)
    names = {tool.name for tool in await gateway.list_tools()}
    assert names == {"files_list", "files_read", "files_write", "gmail_read", "gmail_draft", "gmail_send", "web_fetch"}

"""Helpers the firewall tests import. All keys here are made up."""

from contextlib import contextmanager
from types import SimpleNamespace

from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

FAKE_KEY = "sk-fake-openclaw-01"


@contextmanager
def mcp_request(authorization: str | None):
    """Make in-process tool calls look like an MCP HTTP request with this Authorization header.

    FastMCP reads the current request from the `request_ctx` context variable; the
    tools only look at its headers.
    """
    headers = {} if authorization is None else {"authorization": authorization}
    context = RequestContext(
        request_id=1, meta=None, session=None, lifespan_context=None, request=SimpleNamespace(headers=headers)
    )
    token = request_ctx.set(context)
    try:
        yield
    finally:
        request_ctx.reset(token)

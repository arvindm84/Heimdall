"""Helpers the firewall tests import. All keys, files and folders here are made up."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

from core.contracts.agents import AgentPermissions, FolderAccess
from core.firewall.config import GatewaySettings

FAKE_KEY = "sk-fake-openclaw-01"
AS_OPENCLAW = f"Bearer {FAKE_KEY}"


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


def write_permissions(agents_dir: Path, permissions: AgentPermissions, run_id: str = "run-1", key: str = FAKE_KEY):
    """Write openclaw's permissions.json in the shape B's agent manager writes it."""
    path = agents_dir / "openclaw" / "permissions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {"run_id": run_id, "fake_key": key, "permissions": permissions.model_dump()}
    path.write_text(json.dumps(content), encoding="utf-8")


def make_world(tmp_path: Path, tools=("files_list", "files_read", "files_write")) -> GatewaySettings:
    """Two mounted folders, as the gateway sees them, and openclaw's permissions for them.

    docs:  Private, read only. Host path written POSIX style.
    taxes: Confidential, writable. Host path written Windows style.
    The gateway only uses the last part of each host path: that is the mount name.
    """
    folders = tmp_path / "folders"
    (folders / "docs" / "sub").mkdir(parents=True)
    (folders / "taxes").mkdir(parents=True)
    (folders / "docs" / "notes.txt").write_text("Made-up notes. Call Sam on Tuesday.", encoding="utf-8")
    (folders / "docs" / "sub" / "plan.txt").write_text("Made-up plan.", encoding="utf-8")
    (folders / "taxes" / "summary.txt").write_text("Made-up tax summary.", encoding="utf-8")
    permissions = AgentPermissions(
        tools=list(tools),
        folders=[
            FolderAccess(path="/home/user/docs", label="private"),
            FolderAccess(path="C:\\Users\\user\\taxes", label="confidential", write=True),
        ],
    )
    write_permissions(tmp_path / "agents", permissions)
    return GatewaySettings(
        fake_keys={FAKE_KEY: "openclaw"}, mock=True, agents_dir=tmp_path / "agents", folders_dir=folders
    )


def tiny_pdf(text: str) -> bytes:
    """A one-page PDF showing `text` in Helvetica. Built by hand so tests need no PDF writer."""
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n" % (len(objects) + 1, xref)
    return pdf + b"%%EOF\n"

"""Policy: one test per permission rule. Path rules are in test_files_tool.py."""

from core.contracts.agents import AgentPermissions, FolderAccess
from core.firewall.policy import decide
from core.firewall.session import Session

ALL_TOOLS = AgentPermissions(tools=["files_list", "files_read", "files_write"])
READ_ONLY = FolderAccess(path="/home/user/docs")
WRITABLE = FolderAccess(path="/home/user/out", write=True)


def fresh() -> Session:
    return Session(agent="openclaw", run_id="run-1")


def test_tool_not_in_permissions_is_denied():
    decision = decide("files_read", AgentPermissions(tools=["files_list"]), fresh(), READ_ONLY)
    assert (decision.kind, decision.rule_id) == ("deny", "tool_not_permitted")


def test_unknown_tool_is_denied_even_if_listed():
    decision = decide("shell_run", AgentPermissions(tools=["shell_run"]), fresh(), None)
    assert (decision.kind, decision.rule_id) == ("deny", "unknown_tool")


def test_list_and_read_are_allowed():
    assert decide("files_list", ALL_TOOLS, fresh(), None).rule_id == "files_list_allowed"
    decision = decide("files_read", ALL_TOOLS, fresh(), READ_ONLY)
    assert (decision.kind, decision.rule_id) == ("allow", "files_read_allowed")


def test_write_to_read_only_folder_is_denied():
    decision = decide("files_write", ALL_TOOLS, fresh(), READ_ONLY)
    assert (decision.kind, decision.rule_id) == ("deny", "folder_read_only")


def test_write_to_writable_folder_is_allowed():
    decision = decide("files_write", ALL_TOOLS, fresh(), WRITABLE)
    assert (decision.kind, decision.rule_id) == ("allow", "files_write_allowed")


def test_write_after_untrusted_content_asks():
    session = fresh()
    session.mark_untrusted()
    decision = decide("files_write", ALL_TOOLS, session, WRITABLE)
    assert (decision.kind, decision.rule_id) == ("ask", "write_after_untrusted")

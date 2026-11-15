"""The permission rules: what an agent may do with a tool, given its permissions and session.

One plain function, one `if` block per tool, no rule engine (Progent-style: small
declarative checks on each call). Every decision names the rule that made it, and
that rule_id goes into the event. Checks on the path itself (which folder, escaping
it, size, type) live in core/firewall/tools/files.py.
"""

from dataclasses import dataclass
from typing import Literal

from core.contracts.agents import AgentPermissions, FolderAccess
from core.firewall.permissions import folder_name
from core.firewall.session import Session


@dataclass(frozen=True)
class Decision:
    kind: Literal["allow", "ask", "deny"]
    rule_id: str
    reason: str


def decide(tool: str, permissions: AgentPermissions, session: Session, access: FolderAccess | None) -> Decision:
    """Decide one tool call. `access` is the folder the call's path points into (None if no path)."""
    if tool not in permissions.tools:
        return Decision("deny", "tool_not_permitted", f"{tool} is not in this agent's allowed tools")
    if tool == "files_list":
        reason = "listing allowed folders" if access is None else f"folder {folder_name(access.path)} is allowed"
        return Decision("allow", "files_list_allowed", reason)
    if tool == "files_read":
        return Decision("allow", "files_read_allowed", f"folder {folder_name(access.path)} is allowed")
    if tool == "files_write":
        name = folder_name(access.path)
        if not access.write:
            return Decision("deny", "folder_read_only", f"folder {name} is read only")
        # Untrusted text (an email, a web page) may carry injected instructions, so a
        # write after reading it needs the user (Rule of Two, lethal trifecta).
        if session.untrusted:
            return Decision("ask", "write_after_untrusted", "this session has read untrusted content")
        return Decision("allow", "files_write_allowed", f"folder {name} is writable")
    # Listed in permissions but not a tool the gateway knows: deny by default.
    return Decision("deny", "unknown_tool", f"the gateway has no tool named {tool}")

"""The permission rules: what an agent may do with a tool, given its permissions and session.

One plain function, one `if` block per tool, no rule engine (Progent-style: small
declarative checks on each call). Every decision names the rule that made it, and
that rule_id goes into the event. Checks on the path itself (which folder, escaping
it, size, type) live in core/firewall/tools/files.py.
"""

import re
from dataclasses import dataclass
from typing import Literal

from core.contracts.agents import AgentPermissions, FolderAccess
from core.firewall.labels import Label
from core.firewall.permissions import folder_name
from core.firewall.session import Session


PLACEHOLDER = re.compile(r"\{\{[A-Z]+_\d+\}\}")


@dataclass(frozen=True)
class Decision:
    kind: Literal["allow", "ask", "deny"]
    rule_id: str
    reason: str


def decide(
    tool: str, permissions: AgentPermissions, session: Session, access: FolderAccess | None, outbound: str = ""
) -> Decision:
    """Decide one tool call.

    access: the folder the call's path points into (None if no path).
    outbound: what the call would send out (for web_fetch, the URL).
    """
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
    if tool == "gmail_read":
        return Decision("allow", "gmail_read_allowed", "reading mail is allowed; content is treated as untrusted")
    if tool == "web_fetch":
        # A URL is a way out: a placeholder in it means personal data is on its way somewhere.
        # Placeholders are never filled in a URL, so refuse rather than send the token.
        if PLACEHOLDER.search(outbound):
            return Decision("deny", "placeholder_in_url", "the URL carries a placeholder for personal data")
        # Rule of Two: untrusted input or private data, plus a way out, needs the user.
        if session.untrusted:
            return Decision("ask", "fetch_after_untrusted", "this session has read untrusted content")
        if session.label > Label.PUBLIC:
            return Decision("ask", "fetch_with_private_data", f"this session holds {session.label} data")
        return Decision("allow", "web_fetch_allowed", "fetching a public page")
    # Listed in permissions but not a tool the gateway knows: deny by default.
    return Decision("deny", "unknown_tool", f"the gateway has no tool named {tool}")

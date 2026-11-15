"""The guard every tool call goes through (complete mediation, deny by default).

Order: identify the agent from its key -> load its permissions -> its session ->
check the path -> policy.decide -> ask the user if the rule says so -> run the
tool -> raise the session label -> emit exactly one tool_call event.

Any denial raises PermissionError with the rule and reason, which FastMCP returns
to the agent as an error result, so the agent can tell the user why.
"""

from collections.abc import Callable
from typing import NoReturn

from mcp.server.fastmcp import Context

from core.firewall import core_client, permissions, policy
from core.firewall.config import GatewaySettings
from core.firewall.labels import from_contract
from core.firewall.permissions import AgentRun, NoPermissions
from core.firewall.session import Session, Sessions
from core.firewall.tools import files
from core.firewall.tools.files import Denied, Target

# The tool's own work, run only after the call is allowed: (run, target or None) -> text for the agent.
Work = Callable[[AgentRun, Target | None], str]


class Guard:
    def __init__(self, settings: GatewaySettings, sessions: Sessions):
        self.settings = settings
        self.sessions = sessions

    def identify(self, ctx: Context, tool: str) -> tuple[str, str]:
        """(agent, key) from the bearer key on this MCP call.

        Unknown callers get a tool_denied event (there is no agent to name) and an error.
        """
        try:
            headers = ctx.request_context.request.headers
        except (ValueError, AttributeError):
            # No HTTP request behind this call (an in-process call in tests).
            headers = {}
        key = headers.get("authorization", "").removeprefix("Bearer ").strip()
        agent = self.settings.fake_keys.get(key)
        if agent is None:
            core_client.emit("tool_denied", tool=tool, reason="missing or unknown fake key")
            raise PermissionError("Heimdall: unknown agent")
        return agent, key

    async def run(self, ctx: Context, tool: str, path: str | None, work: Work) -> str:
        """Run one tool call under the policy. `path` is the agent's path argument (None if the call has none)."""
        agent, key = self.identify(ctx, tool)
        try:
            run = permissions.load(self.settings.agents_dir, agent, key)
        except NoPermissions as error:
            self.refuse(agent, tool, path, None, "deny", "no_permissions", str(error))
        session = self.sessions.for_run(agent, run.run_id)

        # Path checks only once the tool itself is allowed, so a denied tool reveals nothing about paths.
        target = None
        if path is not None and tool in run.permissions.tools:
            try:
                target = files.resolve(path, run.permissions, self.settings.folders_dir)
            except Denied as denied:
                self.refuse(agent, tool, path, session, "deny", denied.rule_id, denied.reason)

        decision = policy.decide(tool, run.permissions, session, target.access if target else None)
        if decision.kind == "deny":
            self.refuse(agent, tool, path, session, "deny", decision.rule_id, decision.reason)
        outcome = "allow"
        if decision.kind == "ask":
            if not await self.ask_user(agent, tool, path, decision):
                self.refuse(agent, tool, path, session, "denied_by_user", decision.rule_id, decision.reason)
            outcome = "approved"

        try:
            result = work(run, target)
        except Denied as denied:
            self.refuse(agent, tool, path, session, "deny", denied.rule_id, denied.reason)
        # Only reading content raises the label: the session now holds data at that level.
        if tool == "files_read" and target is not None:
            session.raise_label(from_contract(target.access.label))
        self.record(agent, tool, path, session, outcome, decision.rule_id, decision.reason)
        return result

    async def ask_user(self, agent: str, tool: str, path: str | None, decision: policy.Decision) -> bool:
        """Ask through the core and wait. Anything but an explicit approve is a no."""
        question = f"{agent} wants to use {tool} on {path}. Reason for asking: {decision.reason}."
        try:
            answer = await core_client.ask("approval", agent, question, {"tool": tool, "path": path})
        except Exception:  # noqa: BLE001 - fail closed on any error while asking
            return False
        return answer == "approve"

    def record(
        self, agent: str, tool: str, path: str | None, session: Session | None, decision: str, rule_id: str, reason: str
    ) -> None:
        """The one event for this call. `label` is the session's label after the call."""
        label = str(session.label) if session else "public"
        core_client.emit(
            "tool_call",
            agent=agent,
            tool=tool,
            path=path,
            decision=decision,
            rule_id=rule_id,
            reason=reason,
            label=label,
        )

    def refuse(
        self, agent: str, tool: str, path: str | None, session: Session | None, decision: str, rule_id: str, reason: str
    ) -> NoReturn:
        """Record the refusal, then stop the call with a message the agent can pass on."""
        self.record(agent, tool, path, session, decision, rule_id, reason)
        raise PermissionError(f"Heimdall refused {tool}: {reason} (rule {rule_id})")

"""Per-agent session state for one run of the agent.

B's agent manager writes a fresh run_id every time it opens an agent; a new
run_id starts a fresh session. Sessions live in memory, so a gateway restart also
resets them (a known limit until the vault brings SQLite in Step 2).
"""

import secrets
from dataclasses import dataclass, field

from core.firewall.labels import Label, join


@dataclass
class Session:
    agent: str
    run_id: str
    # Highest label read so far. Only raise_label changes it, and only upward.
    label: Label = Label.PUBLIC
    # True once the agent has read content from outside (email, web). Set from Step 4.
    untrusted: bool = False
    # Random per session, used in Step 4 to wrap untrusted text (Spotlighting).
    delimiter: str = field(default_factory=lambda: secrets.token_hex(8))

    @property
    def id(self) -> str:
        """One id per agent run; the vault numbers placeholders per id."""
        return f"{self.agent}:{self.run_id}"

    def raise_label(self, label: Label) -> None:
        self.label = join(self.label, label)

    def mark_untrusted(self) -> None:
        self.untrusted = True


class Sessions:
    """The current session of each agent."""

    def __init__(self) -> None:
        self._by_agent: dict[str, Session] = {}

    def for_run(self, agent: str, run_id: str) -> Session:
        """This agent's session, starting a fresh one if the run changed."""
        session = self._by_agent.get(agent)
        if session is None or session.run_id != run_id:
            session = Session(agent=agent, run_id=run_id)
            self._by_agent[agent] = session
        return session

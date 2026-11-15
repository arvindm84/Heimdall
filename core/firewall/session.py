"""Per-agent session state for one run of the agent.

B's agent manager writes a fresh run_id every time it opens an agent; a new
run_id starts a fresh session. With a database path, each session's label, untrusted
flag and delimiter are also kept in SQLite: the manager recreates the gateway when
folder mounts change (opening a second agent), and a running agent must not come
back as Public and trusted.
"""

import secrets
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

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
    """The current session of each agent.

    path: the SQLite file to keep sessions in across restarts; None keeps them in memory only (tests).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._by_agent: dict[str, Session] = {}
        self.path = path
        self._db: sqlite3.Connection | None = None

    def db(self) -> sqlite3.Connection | None:
        if self.path is not None and self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.path, check_same_thread=False)
            with self._db:
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS sessions ("
                    " id TEXT PRIMARY KEY, label INTEGER NOT NULL, untrusted INTEGER NOT NULL, delimiter TEXT NOT NULL)"
                )
        return self._db

    def for_run(self, agent: str, run_id: str) -> Session:
        """This agent's session, starting a fresh one if the run changed (or picking it up after a restart)."""
        session = self._by_agent.get(agent)
        if session is None or session.run_id != run_id:
            session = self.load(agent, run_id) or Session(agent=agent, run_id=run_id)
            self._by_agent[agent] = session
        return session

    def load(self, agent: str, run_id: str) -> Session | None:
        db = self.db()
        if db is None:
            return None
        row = db.execute(
            "SELECT label, untrusted, delimiter FROM sessions WHERE id = ?", (f"{agent}:{run_id}",)
        ).fetchone()
        if row is None:
            return None
        return Session(agent=agent, run_id=run_id, label=Label(row[0]), untrusted=bool(row[1]), delimiter=row[2])

    def save(self, session: Session) -> None:
        """Keep this session's state; the guard calls it after every tool call."""
        db = self.db()
        if db is not None:
            with db:
                db.execute(
                    "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?)",
                    (session.id, int(session.label), int(session.untrusted), session.delimiter),
                )

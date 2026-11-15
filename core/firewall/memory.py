"""Each agent's memory: notes kept in the gateway, each with a label (project-plan.md section 6).

A note carries the label of the session that wrote it (a note written after reading
a Confidential file is Confidential) and whether that session had read untrusted
content (mail, a web page). Notes hold placeholders, never real values, because the
agent only ever sees data through the firewall. Agents reach notes only through the
memory_read and memory_write tools, so the guard can raise the reader's label and
mark Confidential notes for the model proxy, as it does for files.

Notes live in the gateway's SQLite file, so they outlive a run and a gateway restart.
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.firewall.labels import Label


@dataclass(frozen=True)
class Note:
    id: int
    text: str
    label: Label
    untrusted: bool
    written: str  # ISO time, UTC


class Memory:
    # memory_read returns the newest notes, up to these limits, so memory can't flood the model.
    MAX_NOTES = 50
    MAX_NOTE_CHARS = 4000

    def __init__(self, path: Path):
        self.path = path
        self._db: sqlite3.Connection | None = None

    def db(self) -> sqlite3.Connection:
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.path, check_same_thread=False)
            with self._db:
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS memory_notes ("
                    " id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT NOT NULL, text TEXT NOT NULL,"
                    " label INTEGER NOT NULL, untrusted INTEGER NOT NULL, written TEXT NOT NULL)"
                )
        return self._db

    def write(self, agent: str, text: str, label: Label, untrusted: bool) -> int:
        """Keep one note. Returns its id."""
        written = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.db() as db:
            cursor = db.execute(
                "INSERT INTO memory_notes (agent, text, label, untrusted, written) VALUES (?, ?, ?, ?, ?)",
                (agent, text, int(label), int(untrusted), written),
            )
        return cursor.lastrowid

    def read(self, agent: str) -> list[Note]:
        """This agent's newest notes, oldest first."""
        rows = self.db().execute(
            "SELECT id, text, label, untrusted, written FROM memory_notes WHERE agent = ? ORDER BY id DESC LIMIT ?",
            (agent, self.MAX_NOTES),
        ).fetchall()
        return [Note(id, text, Label(label), bool(untrusted), written) for id, text, label, untrusted, written in reversed(rows)]

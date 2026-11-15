"""What Confidential text the gateway served each session, and what the user decided about it.

files_read wraps text from a Confidential folder in markers and records it here.
The model proxy looks for that text in requests to a cloud provider (markers first,
then the text itself in case the agent dropped them) and asks the user once per file
per session (core/proxy/consent.py).

Stored in the same SQLite file as the placeholder vault: both hold the user's data,
both live in the gateway's own state folder.
"""

import re
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MARKER = re.compile(r"<</?confidential:([0-9a-f]{12})>>")
# What the agent sees around Confidential text. The closing marker repeats the id so a
# block holding only part of the text still names its file.
WRAP = "<<confidential:{id}>>\n{text}\n<</confidential:{id}>>"
# Text-match fallback: lines this long or longer (after normalizing) count as a match.
# Shorter lines ("Total:", "Yes") would match unrelated text.
MIN_CHUNK_CHARS = 16


@dataclass(frozen=True)
class Served:
    id: str
    file: str  # the agent's path, "<folder>/<file>", shown to the user
    text: str  # the text the agent got (already with placeholders)


def normalize(text: str) -> str:
    """Compare text the way a reader would: same letters, case and spacing ignored."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def chunks(text: str) -> list[str]:
    """The normalized lines of served text that are long enough to match on their own."""
    lines = (normalize(line) for line in text.splitlines())
    return [line for line in lines if len(line) >= MIN_CHUNK_CHARS]


class ConfidentialStore:
    def __init__(self, path: Path):
        self.path = path
        self._db: sqlite3.Connection | None = None

    def db(self) -> sqlite3.Connection:
        """Open the database on first use. check_same_thread=False: the proxy and tools share it."""
        if self._db is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.path, check_same_thread=False)
            with self._db:
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS confidential_markers ("
                    " session TEXT NOT NULL, id TEXT NOT NULL, file TEXT NOT NULL, text TEXT NOT NULL,"
                    " PRIMARY KEY (session, id))"
                )
                self._db.execute(
                    "CREATE TABLE IF NOT EXISTS consent_decisions ("
                    " session TEXT NOT NULL, file TEXT NOT NULL, decision TEXT NOT NULL,"
                    " PRIMARY KEY (session, file))"
                )
        return self._db

    def mark(self, session: str, file: str, text: str) -> str:
        """Record this served text and return it wrapped in markers for the agent."""
        marker_id = secrets.token_hex(6)
        with self.db() as db:
            db.execute("INSERT INTO confidential_markers VALUES (?, ?, ?, ?)", (session, marker_id, file, text))
        return WRAP.format(id=marker_id, text=text)

    def served(self, session: str) -> list[Served]:
        rows = self.db().execute(
            "SELECT id, file, text FROM confidential_markers WHERE session = ?", (session,)
        ).fetchall()
        return [Served(*row) for row in rows]

    def decision(self, session: str, file: str) -> str | None:
        """"approve", "deny", or None if the user hasn't been asked about this file in this session."""
        row = self.db().execute(
            "SELECT decision FROM consent_decisions WHERE session = ? AND file = ?", (session, file)
        ).fetchone()
        return row[0] if row else None

    def record(self, session: str, file: str, decision: str) -> None:
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO consent_decisions VALUES (?, ?, ?)", (session, file, decision))


def files_in(text: str, served: list[Served]) -> set[str]:
    """Which served Confidential files this text holds: by marker id, else by matching text."""
    by_id = {item.id: item.file for item in served}
    found = {by_id[marker_id] for marker_id in MARKER.findall(text) if marker_id in by_id}
    plain = normalize(text)
    for item in served:
        if item.file not in found and any(chunk in plain for chunk in chunks(item.text)):
            found.add(item.file)
    return found
